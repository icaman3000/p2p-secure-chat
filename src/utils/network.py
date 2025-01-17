import os
import sys
import json
import asyncio
import websockets
from datetime import datetime
from sqlalchemy.orm import Session
from src.utils.database import Message, Session as DBSession, get_user_by_id, save_message, get_undelivered_messages, mark_message_as_delivered
from src.utils.crypto import encrypt_message, decrypt_message
from PyQt6.QtCore import QObject, pyqtSignal
import base64

class NetworkManager(QObject):
    message_received = pyqtSignal(dict)
    connection_status_changed = pyqtSignal(bool)
    friend_request_received = pyqtSignal(dict)
    friend_response_received = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.websocket = None
        self.connected_peers = {}
        self.heartbeat_tasks = {}
        self.message_queue = {}
        self.last_heartbeat = {}
        self.heartbeat_interval = 30
        self.user_id = None
        self.username = None
        
    async def start(self, user_id, username=None):
        """启动网络管理器"""
        self.user_id = user_id
        self.username = username
        print(f"Starting network manager for user {user_id} ({username})")
        await self.check_undelivered_messages()
        
    async def send_friend_request(self, recipient_id, request_id):
        """发送好友请求"""
        try:
            message = {
                "type": "friend_request",
                "request_id": request_id,
                "sender_id": self.user_id,
                "sender_username": self.username
            }
            await self.send_message_to_peer(recipient_id, message)
            return True
        except Exception as e:
            print(f"Error sending friend request: {e}")
            return False
            
    async def send_friend_response(self, request_id, sender_id, accepted):
        """发送好友请求响应"""
        try:
            message = {
                "type": "friend_response",
                "request_id": request_id,
                "sender_id": sender_id,
                "recipient_id": self.user_id,
                "recipient_username": self.username,
                "accepted": accepted
            }
            await self.send_message_to_peer(sender_id, message)
            return True
        except Exception as e:
            print(f"Error sending friend response: {e}")
            return False
            
    async def handle_message(self, message):
        """处理接收到的消息"""
        try:
            if message["type"] == "friend_request":
                print(f"Received friend request: {message}")
                self.friend_request_received.emit({
                    "id": message["request_id"],
                    "sender_id": message["sender_id"],
                    "sender_username": message["sender_username"]
                })
            elif message["type"] == "friend_response":
                print(f"Received friend response: {message}")
                self.friend_response_received.emit({
                    "request_id": message["request_id"],
                    "recipient_id": message["recipient_id"],
                    "recipient_username": message["recipient_username"],
                    "accepted": message["accepted"]
                })
            elif message["type"] == "message":
                try:
                    print(f"Processing received message from user {message['sender_id']}")
                    
                    # 解密消息
                    encrypted_data = {
                        "message": message["content"],
                        "key": message["key"]
                    }
                    decrypted_content = decrypt_message(encrypted_data, self.user_id)
                    print(f"Message decrypted successfully")
                    
                    # 保存消息到数据库
                    received_message = save_message(
                        sender_id=message["sender_id"],
                        recipient_id=self.user_id,
                        content=message["content"],  # 保存加密的内容
                        encryption_key=message["key"],
                        timestamp=datetime.fromisoformat(message["timestamp"]) if "timestamp" in message else None
                    )
                    print(f"Message saved to database with ID: {received_message['id']}")
                    
                    # 发送解密后的消息到UI
                    self.message_received.emit({
                        'type': 'message',
                        'sender_id': message["sender_id"],
                        'decrypted_content': decrypted_content,  # 发送解密后的内容
                        'timestamp': message["timestamp"] if "timestamp" in message else datetime.utcnow().isoformat()
                    })
                    
                    # 标记消息为已发送
                    mark_message_as_delivered(received_message['id'])
                    print(f"Message marked as delivered")
                    
                except Exception as e:
                    print(f"Error processing message: {e}")
                    print(f"Message data: {message}")
            else:
                print(f"Unknown message type: {message['type']}")
        except Exception as e:
            print(f"Error handling message: {e}")
            
    async def check_undelivered_messages(self):
        """检查未发送的消息"""
        try:
            messages = get_undelivered_messages(self.user_id)
            print(f"Found {len(messages)} undelivered messages for user {self.user_id}")
            for msg in messages:
                sender = get_user_by_id(msg['sender_id'])
                if sender:
                    print(f"Processing message from {sender.username}")
                    try:
                        # 解密消息
                        if msg.get('encryption_key'):  # 如果有加密密钥
                            encrypted_data = {
                                "message": msg['content'],
                                "key": msg['encryption_key']
                            }
                            decrypted_content = decrypt_message(encrypted_data, self.user_id)
                            print(f"Decrypted message: {decrypted_content}")
                        else:
                            print("Warning: No encryption key found, using raw content")
                            decrypted_content = msg['content']
                        
                        # 将消息标记为已发送
                        mark_message_as_delivered(msg['id'])
                        
                        # 通知UI显示消息
                        self.message_received.emit({
                            'type': 'message',
                            'sender_id': msg['sender_id'],
                            'decrypted_content': decrypted_content,  # 发送解密后的内容
                            'timestamp': msg['timestamp']
                        })
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        print(f"Message data: {msg}")
        except Exception as e:
            print(f"Error checking undelivered messages: {e}")
            
    async def connect_to_peer(self, peer_id, peer_address):
        """连接到对等节点"""
        if peer_id in self.connected_peers:
            return
            
        try:
            websocket = await websockets.connect(f"ws://{peer_address}/ws")
            self.connected_peers[peer_id] = websocket
            
            # 发送身份验证信息
            auth_data = {
                "type": "auth",
                "user_id": self.user_id,
                "username": self.username
            }
            await websocket.send(json.dumps(auth_data))
            
            # 启动心跳检测
            self.heartbeat_tasks[peer_id] = asyncio.create_task(self.heartbeat_check(peer_id))
            
            # 检查是否有未发送的消息
            if peer_id in self.message_queue:
                for msg in self.message_queue[peer_id]:
                    await self.send_message_to_peer(peer_id, msg)
                del self.message_queue[peer_id]
                
        except Exception as e:
            print(f"Error connecting to peer {peer_id}: {e}")
            if peer_id in self.reconnect_attempts:
                self.reconnect_attempts[peer_id] += 1
            else:
                self.reconnect_attempts[peer_id] = 1
                
            if self.reconnect_attempts[peer_id] < self.max_reconnect_attempts:
                print(f"Attempting to reconnect to peer {peer_id}...")
                await asyncio.sleep(5)  # 等待5秒后重试
                await self.connect_to_peer(peer_id, peer_address)
            else:
                print(f"Max reconnection attempts reached for peer {peer_id}")
                
    async def send_message_to_peer(self, peer_id, message):
        """发送消息到对等节点"""
        try:
            if peer_id in self.connected_peers:
                # 准备发送的消息数据，只发送加密的内容
                send_data = {
                    "type": message["type"],
                    "sender_id": message["sender_id"],
                    "recipient_id": message["recipient_id"],
                    "content": message["content"],  # 已经是加密的内容
                    "key": message["key"],
                    "timestamp": message["timestamp"]
                }
                await self.connected_peers[peer_id].send(json.dumps(send_data))
                return True
            else:
                print(f"Peer {peer_id} not connected, queueing message")
                if peer_id not in self.message_queue:
                    self.message_queue[peer_id] = []
                self.message_queue[peer_id].append(message)
                return False
        except Exception as e:
            print(f"Error sending message to peer {peer_id}: {e}")
            return False
            
    async def close_peer_connection(self, peer_id):
        """关闭与对等节点的连接"""
        if peer_id in self.connected_peers:
            try:
                await self.connected_peers[peer_id].close()
            except Exception as e:
                print(f"Error closing connection to peer {peer_id}: {e}")
            finally:
                del self.connected_peers[peer_id]
                if peer_id in self.heartbeat_tasks:
                    self.heartbeat_tasks[peer_id].cancel()
                    del self.heartbeat_tasks[peer_id]
                    
    async def heartbeat_check(self, peer_id):
        """心跳检测"""
        while True:
            try:
                if peer_id not in self.connected_peers:
                    break
                    
                current_time = datetime.utcnow()
                if peer_id in self.last_heartbeat:
                    time_diff = (current_time - self.last_heartbeat[peer_id]).total_seconds()
                    if time_diff > self.heartbeat_interval * 2:
                        print(f"Peer {peer_id} heartbeat timeout")
                        await self.close_peer_connection(peer_id)
                        break
                        
                # 发送心跳
                await self.send_message_to_peer(peer_id, {"type": "heartbeat"})
                self.last_heartbeat[peer_id] = current_time
                
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                print(f"Error in heartbeat check for peer {peer_id}: {e}")
                break
                
    def set_message_callback(self, callback):
        """设置消息回调函数"""
        self.message_callback = callback

    async def stop(self):
        """停止网络管理器"""
        try:
            print("\n=== 开始停止网络管理器 ===")
            
            # 停止所有心跳检查任务
            print(f"1. 正在停止 {len(self.heartbeat_tasks)} 个心跳检测任务...")
            for task in self.heartbeat_tasks.values():
                task.cancel()
            print("2. 心跳检测任务已停止")
            
            # 关闭所有连接
            print(f"3. 正在关闭 {len(self.connected_peers)} 个对等连接...")
            for peer_id, websocket in self.connected_peers.items():
                try:
                    print(f"   - 正在关闭与节点 {peer_id} 的连接...")
                    await websocket.close()
                    print(f"   - 节点 {peer_id} 连接已关闭")
                except Exception as e:
                    print(f"   - 关闭节点 {peer_id} 连接时出错: {e}")
            
            print("4. 正在清理资源...")
            self.connected_peers.clear()
            self.heartbeat_tasks.clear()
            self.message_queue.clear()
            self.last_heartbeat.clear()
            
            print("=== 网络管理器停止完成 ===\n")
            
        except Exception as e:
            print(f"\n!!! 停止网络管理器时出错 !!!")
            print(f"错误详情: {str(e)}")
            print(f"错误类型: {type(e).__name__}\n")

    async def send_message(self, message_data):
        """发送消息"""
        try:
            recipient_id = message_data['recipient_id']
            content = message_data['content']
            
            # 加密消息
            encrypted_data = encrypt_message(content, recipient_id)
            message_data['content'] = encrypted_data['message']
            message_data['key'] = encrypted_data['key']
            
            # 保存原始消息到数据库
            message = save_message(
                sender_id=self.user_id,
                recipient_id=recipient_id,
                content=encrypted_data['message'],  # 保存加密后的内容
                encryption_key=encrypted_data['key'],  # 保存加密密钥
                timestamp=datetime.utcnow()
            )
            print(f"Message saved to database: {message}")
            
            if recipient_id in self.connected_peers:
                # 如果对方在线，直接发送
                await self.connected_peers[recipient_id].send(json.dumps(message_data))
                print(f"Message sent to peer {recipient_id}")
                # 标记消息为已发送
                mark_message_as_delivered(message['id'])
            else:
                # 如果对方不在线，将消息加入队列
                print(f"Peer {recipient_id} not connected, message will be delivered when they come online")
                if recipient_id not in self.message_queue:
                    self.message_queue[recipient_id] = []
                self.message_queue[recipient_id].append(message_data)
            return True
        except Exception as e:
            print(f"Error sending message: {e}")
            return False

network_manager = NetworkManager() 