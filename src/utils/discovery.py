import asyncio
import json
import socket
import netifaces
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

class NodeDiscovery:
    def __init__(self):
        self.discovery_port = int(os.getenv('DISCOVERY_PORT', 8085))
        self.node_port = int(os.getenv('NODE_PORT', 8084))
        self.nodes = {}  # {node_id: {"ip": ip, "port": port, "last_seen": timestamp}}
        self.running = False
        self.node_id = None
    
    def get_broadcast_address(self):
        """获取广播地址"""
        try:
            # 获取默认网关接口
            default_gateway = netifaces.gateways()['default'][netifaces.AF_INET][1]
            # 获取该接口的IP和掩码
            addr = netifaces.ifaddresses(default_gateway)[netifaces.AF_INET][0]
            # 计算广播地址
            ip_parts = [int(x) for x in addr['addr'].split('.')]
            mask_parts = [int(x) for x in addr['netmask'].split('.')]
            broadcast = [(ip & mask) | (~mask & 255) for ip, mask in zip(ip_parts, mask_parts)]
            return '.'.join(str(x) for x in broadcast)
        except:
            return '255.255.255.255'  # 默认广播地址
    
    async def start(self, node_id):
        """启动节点发现服务"""
        try:
            self.node_id = node_id
            self.running = True
            print(f"Starting node discovery service for node {node_id}")
            
            # 创建UDP套接字
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('', self.discovery_port))
            self.sock.setblocking(False)
            print(f"Node discovery service listening on port {self.discovery_port}")
            
            # 启动广播和监听任务
            await asyncio.gather(
                self.broadcast_presence(),
                self.listen_for_nodes()
            )
        except Exception as e:
            print(f"Error starting node discovery service: {e}")
            self.running = False
            raise
    
    async def broadcast_presence(self):
        """定期广播节点存在信息"""
        broadcast_addr = self.get_broadcast_address()
        print(f"Broadcasting presence to {broadcast_addr}:{self.discovery_port}")
        
        while self.running:
            try:
                message = {
                    "type": "node_announce",
                    "node_id": self.node_id,
                    "port": self.node_port,
                    "timestamp": datetime.utcnow().isoformat()
                }
                self.sock.sendto(
                    json.dumps(message).encode(),
                    (broadcast_addr, self.discovery_port)
                )
                print(f"Broadcast sent: {message}")
            except Exception as e:
                print(f"Error broadcasting presence: {e}")
            
            await asyncio.sleep(60)  # 每60秒广播一次
    
    async def listen_for_nodes(self):
        """监听其他节点的广播"""
        print(f"Starting to listen for other nodes on port {self.discovery_port}")
        while self.running:
            try:
                data = await asyncio.get_event_loop().sock_recv(self.sock, 1024)
                if not data:
                    continue
                    
                message = json.loads(data.decode())
                print(f"Received node announcement: {message}")
                
                if message["type"] == "node_announce":
                    node_id = message["node_id"]
                    if node_id != self.node_id:  # 忽略自己的广播
                        try:
                            # 从套接字获取发送者的地址信息
                            addr = self.sock.getpeername()
                            self.nodes[node_id] = {
                                "ip": addr[0],
                                "port": message["port"],
                                "last_seen": message["timestamp"]
                            }
                            print(f"Discovered node {node_id} at {addr[0]}:{message['port']}")
                        except Exception as e:
                            print(f"Error processing node announcement: {e}")
            
            except ConnectionError:
                print("Connection error while listening for nodes")
            except json.JSONDecodeError as e:
                print(f"Received invalid JSON data: {e}")
            except Exception as e:
                print(f"Error listening for nodes: {e}")
            
            await asyncio.sleep(0.1)  # 避免过度占用CPU
    
    async def stop(self):
        """停止节点发现服务"""
        print("Stopping node discovery service")
        self.running = False
        try:
            self.sock.close()
            print("Node discovery service stopped successfully")
        except Exception as e:
            print(f"Error stopping node discovery service: {e}")
    
    def get_active_nodes(self, max_age_minutes=5):
        """获取活跃节点列表"""
        now = datetime.utcnow()
        active_nodes = {}
        
        for node_id, info in self.nodes.items():
            last_seen = datetime.fromisoformat(info["last_seen"])
            age = (now - last_seen).total_seconds() / 60
            
            if age <= max_age_minutes:
                active_nodes[node_id] = info
        
        return active_nodes 