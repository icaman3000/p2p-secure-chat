import asyncio
import json
import socket
import netifaces
from datetime import datetime
import os
from dotenv import load_dotenv
import logging
import time

load_dotenv()

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NodeDiscovery:
    def __init__(self, node_port=0, discovery_port=0, user_id=None):
        self.node_port = node_port
        self.discovery_port = discovery_port
        self.user_id = user_id
        self.sock = None
        self.is_running = False
        self.active_nodes = {}
        self.last_seen = {}
        self.node_timeout = 60  # 节点超时时间(秒)
        self.broadcast_interval = 30  # 广播间隔(秒)
        
    async def start(self):
        """启动节点发现服务"""
        try:
            # 创建UDP套接字
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('0.0.0.0', self.discovery_port))
            
            # Get the actual port number assigned
            self.discovery_port = self.sock.getsockname()[1]
            
            self.is_running = True
            print(f"Node discovery service started on port {self.discovery_port}")
            
            # 启动广播和监听任务
            asyncio.create_task(self.broadcast_presence())
            asyncio.create_task(self.listen_for_nodes())
            
        except Exception as e:
            print(f"Error starting node discovery: {e}")
            if self.sock:
                self.sock.close()
            raise e
            
    async def stop(self):
        """停止节点发现服务"""
        try:
            self.is_running = False
            
            # Cancel all tasks
            tasks = []
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    task.cancel()
                    tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            if self.sock:
                self.sock.close()
                self.sock = None
            
            logger.info("Node discovery service stopped")
        except Exception as e:
            logger.error(f"Error stopping node discovery: {e}")
            raise
            
    async def broadcast_presence(self):
        """广播本节点的存在"""
        try:
            loop = asyncio.get_running_loop()
            while self.is_running:
                try:
                    message = {
                        'type': 'announce',
                        'port': self.node_port
                    }
                    data = json.dumps(message).encode()
                    broadcast_addr = get_broadcast_address()
                    await loop.sock_sendto(self.sock, data, (broadcast_addr, self.discovery_port))
                    logger.info(f"Broadcast message sent to {broadcast_addr}:{self.discovery_port}")
                    await asyncio.sleep(self.broadcast_interval)
                except ConnectionError as e:
                    logger.error(f"Connection error while broadcasting: {e}")
                    await asyncio.sleep(1)  # Wait before retrying
                except Exception as e:
                    logger.error(f"Error broadcasting presence: {e}")
                    await asyncio.sleep(1)  # Wait before retrying
        except asyncio.CancelledError:
            logger.info("Node discovery broadcaster stopped")
            raise
        except Exception as e:
            logger.error(f"Fatal error in broadcast_presence: {e}")
            raise
        
    async def listen_for_nodes(self):
        """监听其他节点的广播消息"""
        try:
            loop = asyncio.get_running_loop()
            while self.is_running:
                try:
                    data, addr = await loop.sock_recvfrom(self.sock, 1024)
                    message = json.loads(data.decode())
                    if message.get('type') == 'announce':
                        port = message.get('port')
                        if port:
                            node_addr = f"{addr[0]}:{port}"
                            logger.info(f"Received node announcement from {node_addr}")
                            await self.on_node_discovered(addr[0], port)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Error decoding message: {e}")
                except ConnectionError as e:
                    logger.error(f"Connection error: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error in listen_for_nodes: {e}")
        except asyncio.CancelledError:
            logger.info("Node discovery listener stopped")
            raise
        except Exception as e:
            logger.error(f"Fatal error in listen_for_nodes: {e}")
            raise
        
    def get_active_nodes(self):
        """获取活跃节点列表"""
        current_time = datetime.utcnow()
        active = {}
        
        for node_id, info in list(self.active_nodes.items()):
            # 检查节点是否超时
            if (current_time - info['last_seen']).total_seconds() < self.node_timeout:
                active[node_id] = info
            else:
                del self.active_nodes[node_id]
                
        return active
        
    def get_node_info(self, node_id):
        """获取指定节点的信息"""
        if node_id in self.active_nodes:
            return self.active_nodes[node_id]
        return None 

    async def on_node_discovered(self, peer_ip: str, peer_port: int):
        """处理发现的新节点
        
        Args:
            peer_ip: 节点IP地址
            peer_port: 节点端口
        """
        try:
            node_addr = f"{peer_ip}:{peer_port}"
            self.active_nodes[node_addr] = {
                'ip': peer_ip,
                'port': peer_port,
                'last_seen': time.time()
            }
            logger.info(f"Added node {node_addr} to active nodes")
        except Exception as e:
            logger.error(f"Error adding node {peer_ip}:{peer_port}: {e}")
            raise

def get_local_ip():
    """获取本机IP地址"""
    try:
        # 获取默认网卡
        default_iface = netifaces.gateways()['default'][netifaces.AF_INET][1]
        # 获取IP地址
        addrs = netifaces.ifaddresses(default_iface)
        return addrs[netifaces.AF_INET][0]['addr']
    except Exception as e:
        print(f"Error getting local IP: {e}")
        return None

def get_broadcast_address():
    """获取广播地址"""
    try:
        # 获取默认网卡
        default_iface = netifaces.gateways()['default'][netifaces.AF_INET][1]
        # 获取广播地址
        addrs = netifaces.ifaddresses(default_iface)
        return addrs[netifaces.AF_INET][0].get('broadcast', '255.255.255.255')
    except Exception as e:
        print(f"Error getting broadcast address: {e}")
        return '255.255.255.255' 