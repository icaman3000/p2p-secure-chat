from aiohttp import web
import aiohttp
import json
from datetime import datetime
import socket
import netifaces

class ChatServer:
    def __init__(self):
        self.app = web.Application()
        self.app.router.add_get('/ws', self.websocket_handler)
        self.clients = {}  # 存储连接的客户端 {user_id: WebSocketResponse}
    
    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        # 获取用户ID
        try:
            user_id = int(request.query.get('user_id'))  # 转换为整数
        except (TypeError, ValueError):
            await ws.close()
            return ws
        
        # 存储客户端连接
        self.clients[user_id] = ws
        print(f"Client {user_id} connected from {request.remote}. Total clients: {len(self.clients)}")
        
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self.handle_message(msg.data)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        
        finally:
            # 清理断开的连接
            if user_id in self.clients:
                del self.clients[user_id]
                print(f"Client {user_id} disconnected. Total clients: {len(self.clients)}")
        
        return ws
    
    async def handle_message(self, data):
        """处理接收到的消息"""
        try:
            print(f"Server received message: {data}")  # Debug log
            message = json.loads(data)
            message_type = message.get("type")
            print(f"Message type: {message_type}")  # Debug log
            
            if message_type == "message":
                recipient_id = int(message.get('recipient_id'))  # 转换为整数
                sender_id = int(message.get('sender_id'))  # 转换为整数
                
                print(f"Processing message: sender={sender_id}, recipient={recipient_id}")
                print(f"Connected clients: {list(self.clients.keys())}")
                
                if recipient_id in self.clients:
                    # 添加时间戳
                    message['timestamp'] = datetime.utcnow().isoformat()
                    message['sender_id'] = sender_id  # 确保使用整数
                    message['recipient_id'] = recipient_id  # 确保使用整数
                    
                    # 转发消息给接收者
                    await self.clients[recipient_id].send_json(message)
                    print(f"Message forwarded from {sender_id} to {recipient_id}")
                else:
                    print(f"Recipient {recipient_id} not found or offline. Available clients: {list(self.clients.keys())}")
            
            elif message_type == "friend_request":
                # 处理好友请求
                recipient_id = int(message.get('recipient_id'))
                sender_id = int(message.get('sender_id'))
                print(f"Processing friend request: from {sender_id} to {recipient_id}")  # Debug log
                
                if recipient_id in self.clients:
                    # 转发好友请求给接收者
                    await self.clients[recipient_id].send_json(message)
                    print(f"Friend request forwarded from {sender_id} to {recipient_id}")
                else:
                    print(f"Recipient {recipient_id} not found or offline")
            
            elif message_type == "friend_response":
                # 处理好友请求的响应
                recipient_id = int(message.get('recipient_id'))  # 原请求的发送者
                sender_id = int(message.get('sender_id'))  # 响应的发送者
                print(f"Processing friend response: from {sender_id} to {recipient_id}")  # Debug log
                
                if recipient_id in self.clients:
                    # 转发响应给原请求的发送者
                    await self.clients[recipient_id].send_json(message)
                    print(f"Friend response forwarded from {sender_id} to {recipient_id}")
                else:
                    print(f"Original requester {recipient_id} not found or offline")
        
        except Exception as e:
            print(f"Error handling message: {e}")
            print(f"Message data: {data}")  # 打印完整的消息数据以便调试
    
    def get_local_ip(self):
        """获取本地IP地址"""
        try:
            # 获取默认网关接口
            default_gateway = netifaces.gateways()['default'][netifaces.AF_INET][1]
            # 获取该接口的IP地址
            ip = netifaces.ifaddresses(default_gateway)[netifaces.AF_INET][0]['addr']
            return ip
        except:
            # 如果上述方法失败，使用替代方法
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # 不需要真正连接
                s.connect(('8.8.8.8', 1))
                local_ip = s.getsockname()[0]
            except:
                local_ip = '127.0.0.1'
            finally:
                s.close()
            return local_ip
    
    def run(self, host='0.0.0.0', port=8082):
        local_ip = self.get_local_ip()
        print(f"Starting server on {host}:{port}")
        print(f"Local IP address: {local_ip}")
        print(f"Clients should connect to: ws://{local_ip}:{port}/ws")
        web.run_app(self.app, host=host, port=port)

if __name__ == '__main__':
    server = ChatServer()
    server.run() 