import asyncio
import json
import websockets
from PyQt6.QtCore import QObject, pyqtSignal
from .discovery import NodeDiscovery
import os
from dotenv import load_dotenv
from datetime import datetime
from collections import deque
import logging

load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NetworkManager(QObject):
    message_received = pyqtSignal(dict)
    connection_status_changed = pyqtSignal(bool)
    friend_request_received = pyqtSignal(dict)
    friend_response_received = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.user_id = None
        self.username = None
        self.websocket = None
        self.running = False
        self.discovery = NodeDiscovery()
        # 使用 discovery 中分配的端口
        self.node_port = self.discovery.node_port
        self.server = None
        self.connected_peers = {}  # {user_id: websocket}
        self.message_queues = {}  # {peer_id: deque()}
        self.reconnect_attempts = {}  # {peer_id: count}
        self.MAX_RECONNECT_ATTEMPTS = 5
        self.HEARTBEAT_INTERVAL = 30  # 秒
    
    async def start_server(self):
        """启动WebSocket服务器"""
        try:
            self.server = await websockets.serve(
                self.handle_connection,
                '0.0.0.0',
                self.node_port
            )
            logger.info(f"P2P node listening on port {self.node_port}")
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            raise
    
    async def handle_connection(self, websocket, path):
        """处理新的WebSocket连接"""
        peer_id = None
        try:
            # 等待对方发送身份信息
            auth_message = await websocket.recv()
            auth_data = json.loads(auth_message)
            peer_id = auth_data.get('user_id')
            
            if peer_id:
                self.connected_peers[peer_id] = websocket
                self.reconnect_attempts[peer_id] = 0  # 重置重连计数
                logger.info(f"Peer {peer_id} connected")
                
                # 启动心跳检测
                asyncio.create_task(self.heartbeat(peer_id, websocket))
                
                # 发送队列中的消息
                if peer_id in self.message_queues:
                    while self.message_queues[peer_id]:
                        message = self.message_queues[peer_id].popleft()
                        await self.send_message_to_peer(peer_id, message)
                
                # 开始接收消息
                while True:
                    message = await websocket.recv()
                    await self.handle_message(json.loads(message))
        
        except websockets.exceptions.ConnectionClosed:
            await self.handle_peer_disconnect(peer_id)
        except Exception as e:
            logger.error(f"Error handling connection: {e}")
            await self.handle_peer_disconnect(peer_id)
    
    async def heartbeat(self, peer_id, websocket):
        """发送心跳包"""
        while self.running and peer_id in self.connected_peers:
            try:
                await websocket.ping()
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            except:
                await self.handle_peer_disconnect(peer_id)
                break
    
    async def handle_peer_disconnect(self, peer_id):
        """处理对等节点断开连接"""
        if peer_id in self.connected_peers:
            del self.connected_peers[peer_id]
            logger.info(f"Peer {peer_id} disconnected")
            
            # 尝试重连
            if peer_id in self.reconnect_attempts and self.reconnect_attempts[peer_id] < self.MAX_RECONNECT_ATTEMPTS:
                self.reconnect_attempts[peer_id] += 1
                logger.info(f"Attempting to reconnect to peer {peer_id} (attempt {self.reconnect_attempts[peer_id]})")
                asyncio.create_task(self.reconnect_to_peer(peer_id))
    
    async def reconnect_to_peer(self, peer_id):
        """重新连接到对等节点"""
        try:
            active_nodes = self.discovery.get_active_nodes()
            if peer_id in active_nodes:
                node_info = active_nodes[peer_id]
                await self.connect_to_peer(peer_id, node_info['ip'], node_info['port'])
        except Exception as e:
            logger.error(f"Failed to reconnect to peer {peer_id}: {e}")
    
    async def send_message_to_peer(self, peer_id, message):
        """发送消息到指定对等节点"""
        try:
            if peer_id in self.connected_peers:
                websocket = self.connected_peers[peer_id]
                await websocket.send(json.dumps(message))
                logger.info(f"Message sent to peer {peer_id}")
                return True
            else:
                # 将消息加入队列
                if peer_id not in self.message_queues:
                    self.message_queues[peer_id] = deque()
                self.message_queues[peer_id].append(message)
                logger.info(f"Message queued for peer {peer_id}")
                return False
        except Exception as e:
            logger.error(f"Error sending message to peer {peer_id}: {e}")
            await self.handle_peer_disconnect(peer_id)
            return False
    
    async def connect_to_peer(self, peer_id, host, port):
        """连接到对等节点"""
        try:
            ws_url = f"ws://{host}:{port}/ws"
            websocket = await websockets.connect(ws_url)
            
            # 发送身份验证信息
            auth_message = {
                "type": "auth",
                "user_id": self.user_id,
                "username": self.username
            }
            await websocket.send(json.dumps(auth_message))
            
            self.connected_peers[peer_id] = websocket
            logger.info(f"Connected to peer {peer_id}")
            
            # 启动心跳检测
            asyncio.create_task(self.heartbeat(peer_id, websocket))
            
            # 发送队列中的消息
            if peer_id in self.message_queues:
                while self.message_queues[peer_id]:
                    message = self.message_queues[peer_id].popleft()
                    await self.send_message_to_peer(peer_id, message)
            
            # 开始接收消息
            while True:
                message = await websocket.recv()
                await self.handle_message(json.loads(message))
        
        except Exception as e:
            logger.error(f"Error connecting to peer {peer_id}: {e}")
            await self.handle_peer_disconnect(peer_id)
    
    async def start(self, user_id, username=None):
        """启动P2P节点"""
        try:
            self.user_id = user_id
            if username:
                self.username = username
            else:
                # 如果没有提供用户名，从数据库获取
                from .database import get_user_by_id
                user = get_user_by_id(user_id)
                self.username = user.username if user else f"User {user_id}"
            
            self.running = True
            
            # 启动WebSocket服务器
            await self.start_server()
            
            # 启动节点发现服务
            await self.discovery.start(user_id)
            
            # 发出连接成功信号
            self.connection_status_changed.emit(True)
            
            # 定期检查和连接新发现的节点
            while self.running:
                try:
                    active_nodes = self.discovery.get_active_nodes()
                    for node_id, info in active_nodes.items():
                        if node_id not in self.connected_peers:
                            asyncio.create_task(
                                self.connect_to_peer(node_id, info['ip'], info['port'])
                            )
                except Exception as e:
                    logger.error(f"Error checking for new nodes: {e}")
                await asyncio.sleep(30)  # 每30秒检查一次
        
        except Exception as e:
            logger.error(f"Error starting network manager: {e}")
            self.connection_status_changed.emit(False)
            raise
    
    async def stop(self):
        """停止P2P节点"""
        self.running = False
        
        # 关闭所有对等连接
        for peer_id, websocket in list(self.connected_peers.items()):
            try:
                await websocket.close()
                logger.info(f"Closed connection to peer {peer_id}")
            except Exception as e:
                logger.error(f"Error closing connection to peer {peer_id}: {e}")
        self.connected_peers.clear()
        
        # 停止服务器
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("WebSocket server stopped")
        
        # 停止节点发现服务
        await self.discovery.stop()
        logger.info("Node discovery service stopped")
        
        # 发出断开连接信号
        self.connection_status_changed.emit(False)
    
    # 添加 disconnect 方法作为 stop 的别名
    async def disconnect(self):
        """停止P2P节点（stop的别名）"""
        await self.stop()
    
    async def send_message(self, message_data):
        """发送消息到指定节点"""
        recipient_id = str(message_data.get('recipient_id'))
        message_data['timestamp'] = datetime.utcnow().isoformat()
        
        success = await self.send_message_to_peer(recipient_id, message_data)
        if not success:
            logger.warning(f"Message to peer {recipient_id} queued for later delivery")
    
    async def handle_message(self, message):
        """处理接收到的消息"""
        try:
            logger.info(f"Received message: {message.get('type')}")
            
            # 根据消息类型处理
            message_type = message.get("type")
            if message_type == "message":
                self.message_received.emit(message)
            elif message_type == "friend_request":
                self.friend_request_received.emit(message)
            elif message_type == "friend_response":
                self.friend_response_received.emit(message)
            else:
                logger.warning(f"Unknown message type: {message_type}")
        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def send_friend_request(self, recipient_id, request_id):
        """发送好友请求"""
        try:
            message = {
                "type": "friend_request",
                "sender_id": self.user_id,
                "sender_username": self.username,
                "recipient_id": recipient_id,
                "id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            success = await self.send_message_to_peer(recipient_id, message)
            return success
        except Exception as e:
            logger.error(f"Error sending friend request: {e}")
            return False
    
    async def send_friend_response(self, request_id, recipient_id, accepted):
        """发送好友请求响应"""
        try:
            message = {
                "type": "friend_response",
                "sender_id": self.user_id,
                "sender_username": self.username,
                "recipient_id": recipient_id,
                "request_id": request_id,
                "accepted": accepted,
                "timestamp": datetime.utcnow().isoformat()
            }
            success = await self.send_message_to_peer(recipient_id, message)
            return success
        except Exception as e:
            logger.error(f"Error sending friend response: {e}")
            return False

# 创建全局 NetworkManager 实例
network_manager = NetworkManager() 