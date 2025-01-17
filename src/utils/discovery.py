import os
import sys
import json
import socket
import asyncio
import netifaces
from datetime import datetime
from src.utils.database import get_user_by_id

class NodeDiscovery:
    def __init__(self, user_id, node_port=None, discovery_port=None):
        self.user_id = user_id
        self.node_port = node_port or 8084
        self.discovery_port = discovery_port or 8085
        self.sock = None
        self.running = False
        self.active_nodes = {}
        self.broadcast_addresses = []
        
    async def start(self):
        """启动节点发现服务"""
        try:
            # 创建UDP套接字
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('0.0.0.0', self.discovery_port))
            self.sock.setblocking(False)
            
            print(f"Node discovery service listening on port {self.discovery_port}")
            
            # 获取所有网络接口的广播地址
            self.broadcast_addresses = self.get_broadcast_addresses()
            print(f"Found broadcast addresses: {self.broadcast_addresses}")
            
            # 启动服务
            self.running = True
            
            # 创建异步任务
            await asyncio.gather(
                self.broadcast_presence(),
                self.listen_for_nodes()
            )
            
        except Exception as e:
            print(f"Error starting node discovery service: {e}")
            if self.sock:
                self.sock.close()
                
    def get_broadcast_addresses(self):
        """获取所有网络接口的广播地址"""
        broadcast_addresses = []
        for interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    if 'broadcast' in addr:
                        broadcast_addresses.append(addr['broadcast'])
        return broadcast_addresses
        
    async def broadcast_presence(self):
        """广播节点存在"""
        while self.running:
            try:
                # 获取用户信息
                user = get_user_by_id(self.user_id)
                if not user:
                    print(f"User {self.user_id} not found")
                    continue
                    
                # 准备广播消息
                announcement = {
                    'type': 'node_announcement',
                    'user_id': self.user_id,
                    'username': user.username,
                    'node_port': self.node_port,
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                # 向所有广播地址发送消息
                for addr in self.broadcast_addresses:
                    try:
                        print(f"Broadcasting presence to {addr}:{self.discovery_port}")
                        self.sock.sendto(
                            json.dumps(announcement).encode(),
                            (addr, self.discovery_port)
                        )
                    except Exception as e:
                        print(f"Error broadcasting to {addr}: {e}")
                        
                await asyncio.sleep(60)  # 每60秒广播一次
                
            except Exception as e:
                print(f"Error in broadcast_presence: {e}")
                await asyncio.sleep(5)  # 出错时等待5秒后重试
                
    async def listen_for_nodes(self):
        """监听其他节点的广播"""
        while self.running:
            try:
                # 创建事件循环
                loop = asyncio.get_event_loop()
                
                # 接收数据
                data, addr = await loop.sock_recv(self.sock, 1024)
                
                if not data:
                    continue
                    
                # 解析消息
                try:
                    announcement = json.loads(data.decode())
                    if announcement.get('type') == 'node_announcement':
                        sender_id = announcement.get('user_id')
                        if sender_id != self.user_id:  # 忽略自己的广播
                            self.active_nodes[sender_id] = {
                                'username': announcement.get('username'),
                                'node_port': announcement.get('node_port'),
                                'address': addr[0],
                                'last_seen': datetime.utcnow()
                            }
                            print(f"Received node announcement from {announcement.get('username')} ({sender_id})")
                except json.JSONDecodeError as e:
                    print(f"Error decoding announcement: {e}")
                    
            except Exception as e:
                print(f"Error listening for nodes: {e}")
                await asyncio.sleep(1)  # 出错时等待1秒后重试
                
    def get_active_nodes(self):
        """获取活跃节点列表"""
        current_time = datetime.utcnow()
        active_nodes = {}
        
        for node_id, info in self.active_nodes.items():
            # 检查节点是否在过去5分钟内有活动
            time_diff = (current_time - info['last_seen']).total_seconds()
            if time_diff <= 300:  # 5分钟 = 300秒
                active_nodes[node_id] = info
                
        return active_nodes
        
    async def stop(self):
        """停止节点发现服务"""
        print("Stopping node discovery service")
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                print(f"Error closing socket: {e}")
                
if __name__ == "__main__":
    # 测试代码
    async def main():
        discovery = NodeDiscovery(1)
        await discovery.start()
        
    asyncio.run(main()) 