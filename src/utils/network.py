import asyncio
import json
import websockets
from PyQt6.QtCore import QObject, pyqtSignal
from .discovery import NodeDiscovery
import os
from dotenv import load_dotenv
from datetime import datetime, UTC
from collections import deque
import logging
import time
from typing import Union

load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NetworkManager(QObject):
    """网络管理器类,负责P2P网络通信"""
    
    message_received = pyqtSignal(int, str)  # 消息接收信号
    friend_request_received = pyqtSignal(int)  # 好友请求信号
    friend_response_received = pyqtSignal(int, bool)  # 好友响应信号
    
    def __init__(self, websocket_port: int = 8090, discovery_port: int = 8091, user_id: int = None):
        """初始化网络管理器
        
        Args:
            websocket_port: WebSocket服务器端口
            discovery_port: 节点发现服务端口
            user_id: 用户ID,可选
        """
        super().__init__()
        
        self.websocket_port = websocket_port
        self.discovery_port = discovery_port
        self.user_id = user_id
        
        self.is_running = False
        self.server = None
        self.discovery = None
        
        # 连接管理
        self.connected_peers = {}  # peer_id -> websocket
        self.last_heartbeat = {}  # peer_id -> timestamp
        self.reconnect_attempts = {}  # peer_id -> attempts
        
        # 消息队列
        self.message_queue = deque()
        
        # 心跳和重连配置
        self.heartbeat_interval = 30  # 心跳间隔（秒）
        self.max_reconnect_attempts = 5  # 最大重连次数
        
    async def start(self):
        """启动网络管理器"""
        if self.is_running:
            return
            
        self.is_running = True
        
        # 启动WebSocket服务器
        self.server = await websockets.serve(
            self.handle_connection,
            '0.0.0.0',
            self.websocket_port
        )
        logger.info(f"P2P node listening on port {self.websocket_port}")
        
        # 启动节点发现服务
        self.discovery = NodeDiscovery(self.websocket_port, self.discovery_port)
        await self.discovery.start()
        
        # 启动心跳检测
        asyncio.create_task(self.heartbeat_check())
    
    async def stop(self):
        """停止网络管理器"""
        if not self.is_running:
            return

        self.is_running = False
        
        # Cancel all tasks
        tasks = []
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task():
                task.cancel()
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0.1)  # Give tasks time to clean up
        
        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        
        # Stop discovery service
        if self.discovery:
            await self.discovery.stop()
            self.discovery = None
        
        # Clear state
        self.connected_peers = {}
        self.last_heartbeat.clear()
        self.reconnect_attempts.clear()
        self.message_queue.clear()
        
        logger.info("Network manager stopped")
    
    async def disconnect(self):
        """断开所有连接"""
        try:
            self.connected_peers.clear()
            self.is_running = False
            if self.server:
                self.server.close()
                await self.server.wait_closed()
        except Exception as e:
            logging.error(f"Error disconnecting: {e}")
            raise e
    
    async def send_message(self, recipient_id: int, content: Union[str, dict]) -> bool:
        """
        Send a message to a specific recipient.
        """
        try:
            message = {
                "type": "message",
                "sender_id": self.user_id,
                "recipient_id": recipient_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "content": content if isinstance(content, str) else content["content"]
            }
            
            # If peer is connected, send directly
            if recipient_id in self.connected_peers:
                peer = self.connected_peers[recipient_id]
                await peer.send(json.dumps(message))
            else:
                # Otherwise queue the message
                self.message_queue.append(message)
            
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
    
    async def handle_connection(self, websocket, path):
        """处理新的WebSocket连接"""
        try:
            # 等待身份验证消息
            auth_message = await websocket.recv()
            auth_data = json.loads(auth_message)
            
            if auth_data["type"] == "auth":
                peer_id = auth_data["user_id"]
                self.connected_peers[peer_id] = websocket
                
                # 发送队列中的消息
                for message in self.message_queue:
                    if message["recipient_id"] == peer_id:
                        await websocket.send(json.dumps(message))
                
                # 移除已发送的消息
                self.message_queue = [
                    m for m in self.message_queue 
                    if m["recipient_id"] != peer_id
                ]
                
                # 开始消息处理循环
                try:
                    while True:
                        message = await websocket.recv()
                        await self.handle_message(json.loads(message))
                except websockets.exceptions.ConnectionClosed:
                    await self.handle_peer_disconnect(peer_id)
                    
        except Exception as e:
            logging.error(f"Error handling connection: {e}")
    
    async def handle_message(self, message):
        """处理接收到的消息"""
        try:
            if message["type"] == "message":
                # 保存消息到数据库
                save_message(
                    sender_id=message["sender_id"],
                    recipient_id=message["recipient_id"],
                    content=message["content"],
                    timestamp=message["timestamp"]
                )
            elif message["type"] == "friend_request":
                # 处理好友请求
                pass
            elif message["type"] == "friend_response":
                # 处理好友响应
                pass
        except Exception as e:
            logging.error(f"Error handling message: {e}")
    
    async def handle_peer_disconnect(self, peer_id):
        """处理对等节点断开连接"""
        try:
            if peer_id in self.connected_peers:
                del self.connected_peers[peer_id]
            
            # 尝试重连
            if peer_id not in self.reconnect_attempts:
                self.reconnect_attempts[peer_id] = 0
            
            if self.reconnect_attempts[peer_id] < self.max_reconnect_attempts:
                self.reconnect_attempts[peer_id] += 1
                await asyncio.sleep(5)  # 等待5秒后重试
                await self.connect_to_peer(peer_id)
            else:
                logging.warning(f"Max reconnection attempts reached for peer {peer_id}")
        except Exception as e:
            logging.error(f"Error handling peer disconnect: {e}")
    
    async def connect_to_peer(self, peer_id):
        """连接到对等节点"""
        try:
            # 获取节点信息
            node_info = self.discovery.get_node_info(peer_id)
            if not node_info:
                return False
            
            # 建立WebSocket连接
            uri = f"ws://{node_info['host']}:{node_info['port']}/ws"
            websocket = await websockets.connect(uri)
            
            # 发送身份验证消息
            auth_message = {
                "type": "auth",
                "user_id": self.user_id,
                "username": self.username
            }
            await websocket.send(json.dumps(auth_message))
            
            # 保存连接
            self.connected_peers[peer_id] = websocket
            self.reconnect_attempts[peer_id] = 0
            
            return True
        except Exception as e:
            logging.error(f"Error connecting to peer: {e}")
            return False
    
    async def heartbeat_check(self):
        """检查连接的节点心跳"""
        try:
            while self.is_running:
                try:
                    current_time = time.time()
                    for peer_id in list(self.connected_peers.keys()):
                        last_heartbeat = self.last_heartbeat.get(peer_id, 0)
                        if current_time - last_heartbeat > self.heartbeat_interval * 2:
                            logger.warning(f"Node {peer_id} heartbeat timeout")
                            await self.disconnect_peer(peer_id)
                    await asyncio.sleep(self.heartbeat_interval)
                except Exception as e:
                    logger.error(f"Error in heartbeat check: {e}")
                    await asyncio.sleep(1)  # Wait before retrying
        except asyncio.CancelledError:
            logger.info("Heartbeat check stopped")
            raise
        except Exception as e:
            logger.error(f"Fatal error in heartbeat check: {e}")
            raise
    
    async def send_friend_request(self, recipient_id):
        """发送好友请求"""
        try:
            message = {
                "type": "friend_request",
                "sender_id": self.user_id,
                "sender_username": self.username,
                "recipient_id": recipient_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if recipient_id in self.connected_peers:
                peer = self.connected_peers[recipient_id]
                await peer.send(json.dumps(message))
            else:
                self.message_queue.append(message)
            
            return True
        except Exception as e:
            logging.error(f"Error sending friend request: {e}")
            return False
    
    async def handle_friend_response(self, recipient_id, accepted):
        """处理好友请求响应"""
        try:
            message = {
                "type": "friend_response",
                "sender_id": self.user_id,
                "sender_username": self.username,
                "recipient_id": recipient_id,
                "accepted": accepted,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if recipient_id in self.connected_peers:
                peer = self.connected_peers[recipient_id]
                await peer.send(json.dumps(message))
            else:
                self.message_queue.append(message)
            
            return True
        except Exception as e:
            logging.error(f"Error handling friend response: {e}")
            return False

# 创建全局 NetworkManager 实例
network_manager = NetworkManager() 