import asyncio
import logging
import socket
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from .stun_client import StunClient

@dataclass
class PeerInfo:
    """对等端信息"""
    id: str
    local_addr: Optional[Tuple[str, int]] = None
    public_addr: Optional[Tuple[str, int]] = None
    connection: Optional[asyncio.StreamWriter] = None

class ConnectionManager:
    """连接管理器 - 专注于安全的点对点通信"""
    
    def __init__(self):
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
        
        # 添加消息处理相关的配置
        self.max_message_size = 1024 * 1024  # 1MB
        self.read_buffer_size = 64 * 1024    # 64KB
        
    def set_message_handler(self, handler):
        """设置消息处理回调函数"""
        self.message_handler = handler
        
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
            logging.info(f"本地服务器启动在端口 {self.local_port}")
            
            # 获取 STUN 绑定信息
            await self._get_stun_bindings()
            
        except Exception as e:
            logging.error(f"启动连接管理器失败: {e}")
            raise
            
    async def _get_stun_bindings(self) -> None:
        """获取 STUN 绑定信息"""
        successful_bindings = 0
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
                        successful_bindings += 1
                        logging.info(f"STUN 绑定成功: {binding}")
                        
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
            # 配置读取缓冲区大小
            reader._limit = self.max_message_size
            
            while True:
                try:
                    # 读取消息长度（4字节整数）
                    length_data = await reader.readexactly(4)
                    message_length = int.from_bytes(length_data, 'big')
                    
                    if message_length > self.max_message_size:
                        logging.error(f"消息太大: {message_length} bytes")
                        break
                        
                    # 读取消息内容
                    message_data = await reader.readexactly(message_length)
                    message = json.loads(message_data.decode())
                    
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
                    break
                except json.JSONDecodeError as e:
                    logging.error(f"无效的消息格式: {e}")
                    continue
                except Exception as e:
                    logging.error(f"处理消息时出错: {e}")
                    break
                    
        except Exception as e:
            logging.error(f"处理连接失败: {e}")
        finally:
            if peer_id and peer_id in self.peers:
                del self.peers[peer_id]
                # 如果连接断开，尝试重连
                if addr:
                    self._start_reconnect_task(peer_id, addr)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            
    async def send_message(self, peer_id: str, message: dict) -> bool:
        """发送消息到指定对等端"""
        try:
            peer = self.peers.get(peer_id)
            if not peer or not peer.connection:
                logging.warning(f"对等端 {peer_id} 未连接")
                return False
                
            # 序列化消息
            message_data = json.dumps(message).encode()
            message_length = len(message_data)
            
            if message_length > self.max_message_size:
                logging.error(f"消息太大: {message_length} bytes")
                return False
                
            # 发送消息长度和内容
            length_data = message_length.to_bytes(4, 'big')
            peer.connection.write(length_data)
            peer.connection.write(message_data)
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
            "peer_count": len(self.peers),
            "active_reconnections": len(self.reconnect_tasks)
        } 