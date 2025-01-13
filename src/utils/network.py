import asyncio
import json
import websockets
from PyQt6.QtCore import QObject, pyqtSignal
from .discovery import NodeDiscovery
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

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
        self.node_port = int(os.getenv('NODE_PORT', 8084))
        self.discovery = NodeDiscovery()
        self.server = None
        self.connected_peers = {}  # {user_id: websocket}
    
    async def start_server(self):
        """启动WebSocket服务器"""
        self.server = await websockets.serve(
            self.handle_connection,
            '0.0.0.0',
            self.node_port
        )
        print(f"P2P node listening on port {self.node_port}")
    
    async def handle_connection(self, websocket, path):
        """处理新的WebSocket连接"""
        try:
            # 等待对方发送身份信息
            auth_message = await websocket.recv()
            auth_data = json.loads(auth_message)
            peer_id = auth_data.get('user_id')
            
            if peer_id:
                self.connected_peers[peer_id] = websocket
                print(f"Peer {peer_id} connected")
                
                # 开始接收消息
                while True:
                    message = await websocket.recv()
                    await self.handle_message(json.loads(message))
        
        except websockets.exceptions.ConnectionClosed:
            if peer_id in self.connected_peers:
                del self.connected_peers[peer_id]
                print(f"Peer {peer_id} disconnected")
        except Exception as e:
            print(f"Error handling connection: {e}")
    
    async def connect_to_peer(self, peer_id, host, port):
        """连接到对等节点"""
        try:
            ws_url = f"ws://{host}:{port}/ws"
            websocket = await websockets.connect(ws_url)
            
            # 发送身份验证信息
            auth_message = {
                "type": "auth",
                "user_id": self.user_id
            }
            await websocket.send(json.dumps(auth_message))
            
            self.connected_peers[peer_id] = websocket
            print(f"Connected to peer {peer_id}")
            
            # 开始接收消息
            while True:
                message = await websocket.recv()
                await self.handle_message(json.loads(message))
        
        except Exception as e:
            print(f"Error connecting to peer {peer_id}: {e}")
            if peer_id in self.connected_peers:
                del self.connected_peers[peer_id]
    
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
                active_nodes = self.discovery.get_active_nodes()
                for node_id, info in active_nodes.items():
                    if node_id not in self.connected_peers:
                        asyncio.create_task(
                            self.connect_to_peer(node_id, info['ip'], info['port'])
                        )
                await asyncio.sleep(30)  # 每30秒检查一次
        except Exception as e:
            print(f"Error starting network manager: {e}")
            self.connection_status_changed.emit(False)
            raise
    
    async def stop(self):
        """停止P2P节点"""
        self.running = False
        
        # 关闭所有对等连接
        for websocket in self.connected_peers.values():
            await websocket.close()
        self.connected_peers.clear()
        
        # 停止服务器
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        # 停止节点发现服务
        await self.discovery.stop()
        
        # 发出断开连接信号
        self.connection_status_changed.emit(False)
    
    # 添加 disconnect 方法作为 stop 的别名
    async def disconnect(self):
        """停止P2P节点（stop的别名）"""
        await self.stop()
    
    async def send_message(self, message_data):
        """发送消息到指定节点"""
        recipient_id = str(message_data.get('recipient_id'))
        
        if recipient_id in self.connected_peers:
            try:
                websocket = self.connected_peers[recipient_id]
                await websocket.send(json.dumps(message_data))
                print(f"Message sent to {recipient_id}")
            except Exception as e:
                print(f"Error sending message to {recipient_id}: {e}")
                # 如果发送失败，移除连接
                del self.connected_peers[recipient_id]
        else:
            print(f"Peer {recipient_id} not connected")
    
    async def handle_message(self, message):
        """处理接收到的消息"""
        # 发出消息接收信号
        self.message_received.emit(message)
        
        # 根据消息类型处理
        if message.get("type") == "friend_request":
            self.friend_request_received.emit(message)
        elif message.get("type") == "friend_response":
            self.friend_response_received.emit(message) 

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
            await self.send_message(message)
            return True
        except Exception as e:
            print(f"Error sending friend request: {e}")
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
            await self.send_message(message)
            return True
        except Exception as e:
            print(f"Error sending friend response: {e}")
            return False

# 创建全局 NetworkManager 实例
network_manager = NetworkManager() 