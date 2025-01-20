import asyncio
import logging
import socket
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal
from .stun_client import StunClient
from datetime import datetime

@dataclass
class PeerInfo:
    """对等端信息"""
    id: str
    local_addr: Optional[Tuple[str, int]] = None
    public_addr: Optional[Tuple[str, int]] = None
    connection: Optional[asyncio.StreamWriter] = None

class SyncMessageType:
    """同步消息类型"""
    DEVICE_DISCOVERY = 'device_discovery'     # 设备发现
    DEVICE_RESPONSE = 'device_response'       # 设备响应
    SYNC_REQUEST = 'sync_request'            # 同步请求
    SYNC_DATA = 'sync_data'                  # 同步数据
    FRIEND_DATA_REQUEST = 'friend_data_request'  # 向好友请求数据
    FRIEND_DATA_RESPONSE = 'friend_data_response'  # 好友响应数据

class ConnectionManager(QObject):
    """连接管理器 - 专注于安全的点对点通信"""
    
    # 定义信号
    network_info_updated = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        # STUN 服务器列表 - 使用可靠的公共 STUN 服务器
        self.stun_servers = [
            "stun.voip.blackberry.com:3478",  # Blackberry
            "stun.voipgate.com:3478",         # VoIPGate
            "stun.qq.com:3478",               # Tencent
            "stun.miwifi.com:3478"            # Xiaomi
        ]
        
        self.local_port = None  # 本地监听端口
        self.server = None      # 本地服务器
        self.peers: Dict[str, PeerInfo] = {}  # 对等端信息
        self.stun_results: List[Dict] = []    # STUN 绑定结果
        self.message_handler = None  # 消息处理回调函数
        self.reconnect_tasks: Dict[str, asyncio.Task] = {}  # 重连任务
        self.max_reconnect_attempts = 3  # 最大重连次数
        self.reconnect_delay = 2.0  # 重连延迟（秒）
        
        # 用户信息
        self.user_id = None
        self.username = None
        
        # 网络信息
        self.network_info = {
            'local_ip': None,
            'public_ip': None,
            'stun_results': []
        }
        
        self.device_id = self._generate_device_id()
        
    def set_user_info(self, user_id: int, username: str):
        """设置用户信息"""
        self.user_id = user_id
        self.username = username
        
    def set_message_handler(self, handler):
        """设置消息处理回调函数"""
        self.message_handler = handler
        
    def _update_network_info(self, **kwargs):
        """更新网络信息并发出信号"""
        self.network_info.update(kwargs)
        self.network_info_updated.emit(self.network_info)
        
    async def start(self, port: int = 0) -> None:
        """启动连接管理器"""
        try:
            # 启动本地服务器
            self.server = await asyncio.start_server(
                self._handle_connection,
                host='0.0.0.0',
                port=port
            )
            self.local_port = self.server.sockets[0].getsockname()[1]
            
            # 获取本地IP
            local_ip = socket.gethostbyname(socket.gethostname())
            self._update_network_info(local_ip=local_ip)
            logging.info(f"本地服务器启动在端口 {self.local_port}")
            
            # 获取 STUN 绑定信息
            await self._get_stun_bindings()
            
        except Exception as e:
            logging.error(f"启动连接管理器失败: {e}")
            raise
            
    async def _get_stun_bindings(self) -> None:
        """获取 STUN 绑定信息"""
        successful_bindings = 0
        stun_results = []
        
        for server in self.stun_servers:
            try:
                host, port = server.split(":")
                port = int(port)
                
                client = StunClient(host, port)
                await client.connect()
                
                try:
                    binding = await client.get_binding()
                    if binding:
                        self.stun_results.append(binding)
                        stun_results.append(binding)
                        successful_bindings += 1
                        logging.info(f"STUN 绑定成功: {binding}")
                        
                        # 更新网络信息
                        if 'mapped_address' in binding:
                            self._update_network_info(
                                public_ip=binding['mapped_address'][0],
                                stun_results=stun_results
                            )
                        
                        # 如果已经有两个成功的绑定，提前退出
                        if successful_bindings >= 2:
                            break
                finally:
                    await client.close()
                    
            except Exception as e:
                logging.warning(f"STUN 服务器 {server} 绑定失败: {e}")
                
    async def connect_to_peer(self, peer_id: str, peer_addr: Tuple[str, int]) -> bool:
        """连接到对等端"""
        try:
            # 1. 尝试直接连接
            result = await self._try_direct_connection(peer_addr)
            if result:
                reader, writer = result
                self.peers[peer_id] = PeerInfo(
                    id=peer_id,
                    local_addr=peer_addr,
                    connection=writer
                )
                logging.info(f"与对等端 {peer_id} 建立直接连接成功")
                return True
                
            # 2. 尝试通过公网地址连接
            for stun_result in self.stun_results:
                mapped_addr = stun_result.get("mapped_address")
                if mapped_addr:
                    result = await self._try_direct_connection(mapped_addr)
                    if result:
                        reader, writer = result
                        self.peers[peer_id] = PeerInfo(
                            id=peer_id,
                            public_addr=mapped_addr,
                            connection=writer
                        )
                        logging.info(f"与对等端 {peer_id} 通过 STUN 地址建立连接成功")
                        return True
                    
            logging.warning(f"无法与对等端 {peer_id} 建立连接")
            # 启动重连任务
            self._start_reconnect_task(peer_id, peer_addr)
            return False
            
        except Exception as e:
            logging.error(f"连接对等端 {peer_id} 失败: {e}")
            return False
            
    def _start_reconnect_task(self, peer_id: str, peer_addr: Tuple[str, int]):
        """启动重连任务"""
        if peer_id not in self.reconnect_tasks:
            task = asyncio.create_task(self._reconnect_loop(peer_id, peer_addr))
            self.reconnect_tasks[peer_id] = task
            
    async def _reconnect_loop(self, peer_id: str, peer_addr: Tuple[str, int]):
        """重连循环"""
        attempts = 0
        while attempts < self.max_reconnect_attempts:
            await asyncio.sleep(self.reconnect_delay)
            logging.info(f"尝试重新连接到对等端 {peer_id}，第 {attempts + 1} 次尝试")
            
            if await self.connect_to_peer(peer_id, peer_addr):
                logging.info(f"重新连接到对等端 {peer_id} 成功")
                break
                
            attempts += 1
            
        if peer_id in self.reconnect_tasks:
            del self.reconnect_tasks[peer_id]
            
    async def _try_direct_connection(self, addr: Tuple[str, int]) -> Optional[Tuple[asyncio.StreamReader, asyncio.StreamWriter]]:
        """尝试直接连接"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(addr[0], addr[1]),
                timeout=2.0
            )
            return reader, writer
        except asyncio.TimeoutError:
            logging.warning(f"连接到 {addr} 超时")
            return None
        except Exception as e:
            logging.warning(f"连接到 {addr} 失败: {e}")
            return None
            
    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """处理新的连接"""
        addr = writer.get_extra_info('peername')
        logging.info(f"收到来自 {addr} 的连接")
        peer_id = None
        
        try:
            # 设置更大的消息限制
            reader._limit = 1024 * 1024  # 1MB
            
            while True:
                try:
                    data = await reader.readuntil(b'\n')
                    message = json.loads(data.decode().strip())
                    
                    # 处理身份验证消息
                    if not peer_id and 'peer_id' in message:
                        peer_id = message['peer_id']
                        self.peers[peer_id] = PeerInfo(
                            id=peer_id,
                            local_addr=addr,
                            connection=writer
                        )
                        logging.info(f"对等端 {peer_id} 已认证")
                        continue
                    
                    # 处理普通消息
                    if peer_id and self.message_handler:
                        await self.message_handler(peer_id, message)
                        
                except asyncio.IncompleteReadError:
                    if not writer.is_closing():
                        writer.close()
                    break
                except json.JSONDecodeError as e:
                    logging.error(f"无效的消息格式: {e}")
                    continue
                except Exception as e:
                    logging.error(f"处理消息时出错: {e}")
                    if not writer.is_closing():
                        writer.close()
                    break
                    
        except Exception as e:
            logging.error(f"处理连接失败: {e}")
        finally:
            if peer_id and peer_id in self.peers:
                del self.peers[peer_id]
                # 如果连接断开，尝试重连
                if addr:
                    self._start_reconnect_task(peer_id, addr)
            if not writer.is_closing():
                writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            
    async def send_message(self, peer_id: str, message: dict) -> bool:
        """发送消息到指定对等端"""
        try:
            # 检查是否已经连接
            peer = self.peers.get(peer_id)
            if not peer or not peer.connection or peer.connection.is_closing():
                # 尝试建立连接
                if not await self._establish_connection(peer_id):
                    logging.warning(f"对等端 {peer_id} 未连接")
                    return False
                    
                # 重新获取对等端信息
                peer = self.peers.get(peer_id)
                if not peer or not peer.connection:
                    return False
                    
            if peer.connection.is_closing():
                logging.warning(f"对等端 {peer_id} 连接已关闭")
                return False
                
            # 发送消息，添加分隔符
            data = json.dumps(message).encode() + b'\n'
            peer.connection.write(data)
            await peer.connection.drain()
            return True
            
        except Exception as e:
            logging.error(f"发送消息失败: {e}")
            # 如果发送失败，移除对等端并尝试重连
            if peer_id in self.peers:
                peer = self.peers.pop(peer_id)
                if peer.local_addr:
                    self._start_reconnect_task(peer_id, peer.local_addr)
            return False
            
    async def _establish_connection(self, peer_id: str) -> bool:
        """建立与对等端的连接"""
        try:
            # 尝试直接连接
            for port in range(8000, 9000):
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection('127.0.0.1', port),
                        timeout=0.5
                    )
                    
                    # 发送身份验证消息
                    auth_message = {
                        "type": "auth",
                        "peer_id": self.user_id,
                        "username": self.username,
                        "timestamp": datetime.now().timestamp()
                    }
                    
                    data = json.dumps(auth_message).encode() + b'\n'
                    writer.write(data)
                    await writer.drain()
                    
                    # 等待身份验证回复
                    try:
                        data = await asyncio.wait_for(
                            reader.readuntil(b'\n'),
                            timeout=2.0
                        )
                        response = json.loads(data.decode().strip())
                        
                        if response.get("type") == "auth_reply":
                            # 保存连接信息
                            self.peers[peer_id] = PeerInfo(
                                id=peer_id,
                                local_addr=('127.0.0.1', port),
                                connection=writer
                            )
                            logging.info(f"与对等端 {peer_id} 建立连接成功")
                            return True
                            
                    except asyncio.TimeoutError:
                        writer.close()
                        continue
                        
                except (ConnectionRefusedError, asyncio.TimeoutError):
                    continue
                    
            logging.warning(f"无法与对等端 {peer_id} 建立连接")
            return False
            
        except Exception as e:
            logging.error(f"建立连接失败: {e}")
            return False
            
    async def stop(self):
        """停止连接管理器"""
        try:
            # 取消所有重连任务
            for task in self.reconnect_tasks.values():
                task.cancel()
            self.reconnect_tasks.clear()
            
            # 关闭所有对等连接
            for peer_id, peer in list(self.peers.items()):
                if peer.connection:
                    peer.connection.close()
                    try:
                        await asyncio.wait_for(peer.connection.wait_closed(), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
                    
            # 关闭服务器
            if self.server:
                self.server.close()
                try:
                    await asyncio.wait_for(self.server.wait_closed(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
                    
            logging.info("连接管理器已停止")
            
        except Exception as e:
            logging.error(f"停止连接管理器时出错: {e}")
            
    def get_connection_info(self) -> Dict:
        """获取连接信息"""
        return {
            "local_port": self.local_port,
            "stun_results": self.stun_results,
            "peer_count": len(self.peers)
        }

    def _generate_device_id(self) -> str:
        """生成设备ID"""
        import uuid
        import platform
        import hashlib
        
        # 获取系统信息
        system_info = {
            'platform': platform.system(),
            'node': platform.node(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'uuid': str(uuid.uuid4())
        }
        
        # 生成唯一标识
        info_str = str(system_info)
        return hashlib.sha256(info_str.encode()).hexdigest()[:16]
        
    async def broadcast_device_discovery(self):
        """广播设备发现消息"""
        discovery_message = {
            'type': SyncMessageType.DEVICE_DISCOVERY,
            'user_id': self.user_id,
            'username': self.username,
            'device_id': self.device_id,
            'timestamp': datetime.now().timestamp()
        }
        
        # 广播消息到所有可能的端口
        for port in range(8000, 9000):
            try:
                await self.send_message_to_port('127.0.0.1', port, discovery_message)
            except Exception as e:
                logger.debug(f"Failed to send discovery message to port {port}: {e}")
                
    async def handle_device_discovery(self, message: dict):
        """处理设备发现消息"""
        if message['user_id'] == self.user_id and message['device_id'] != self.device_id:
            # 响应其他设备的发现请求
            response = {
                'type': SyncMessageType.DEVICE_RESPONSE,
                'user_id': self.user_id,
                'username': self.username,
                'device_id': self.device_id,
                'timestamp': datetime.now().timestamp()
            }
            await self.send_message(message['device_id'], response)
            
    async def handle_device_response(self, message: dict):
        """处理设备响应消息"""
        if message['user_id'] == self.user_id:
            # 发送同步请求
            sync_request = {
                'type': SyncMessageType.SYNC_REQUEST,
                'user_id': self.user_id,
                'device_id': self.device_id,
                'timestamp': datetime.now().timestamp()
            }
            await self.send_message(message['device_id'], sync_request)
            
    async def handle_sync_request(self, message: dict):
        """处理同步请求"""
        if message['user_id'] == self.user_id:
            # 获取本地数据
            from src.utils.database import get_friend_list, get_messages_between_users
            
            friends = get_friend_list(self.user_id)
            messages = []
            for friend in friends:
                friend_messages = get_messages_between_users(self.user_id, friend['id'])
                messages.extend(friend_messages)
                
            # 发送同步数据
            sync_data = {
                'type': SyncMessageType.SYNC_DATA,
                'user_id': self.user_id,
                'device_id': self.device_id,
                'timestamp': datetime.now().timestamp(),
                'data': {
                    'friends': friends,
                    'messages': messages
                }
            }
            await self.send_message(message['device_id'], sync_data)
            
    async def handle_sync_data(self, message: dict):
        """处理同步数据"""
        if message['user_id'] == self.user_id:
            try:
                # 更新本地数据
                from src.utils.database import add_friend, save_message
                
                data = message['data']
                
                # 同步好友列表
                for friend in data['friends']:
                    add_friend(self.user_id, friend['id'], friend['username'])
                    
                # 同步消息
                for msg in data['messages']:
                    save_message(
                        msg['sender_id'],
                        msg['recipient_id'],
                        msg['content'],
                        msg['timestamp'] if 'timestamp' in msg else None,
                        msg['encryption_key'] if 'encryption_key' in msg else None
                    )
                    
                # 更新同步时间
                from src.utils.database import update_device_sync_time
                update_device_sync_time(self.device_id)
                
                logger.info("Data synchronization completed successfully")
                
            except Exception as e:
                logger.error(f"Error processing sync data: {e}")
                
    async def _handle_message(self, peer_id: str, message: dict):
        """处理接收到的消息"""
        try:
            msg_type = message.get('type')
            
            # 处理同步相关消息
            if msg_type == SyncMessageType.DEVICE_DISCOVERY:
                await self.handle_device_discovery(message)
            elif msg_type == SyncMessageType.DEVICE_RESPONSE:
                await self.handle_device_response(message)
            elif msg_type == SyncMessageType.SYNC_REQUEST:
                await self.handle_sync_request(message)
            elif msg_type == SyncMessageType.SYNC_DATA:
                await self.handle_sync_data(message)
            else:
                # 处理其他类型的消息
                if self.message_handler:
                    await self.message_handler(peer_id, message)
                    
        except Exception as e:
            logger.error(f"Error handling message: {e}") 