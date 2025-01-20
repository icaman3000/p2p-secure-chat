import asyncio
import logging
import socket
import struct
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
import random
import hmac
import hashlib

@dataclass
class StunMessage:
    """STUN 消息结构"""
    message_type: int
    message_length: int
    magic_cookie: int
    transaction_id: bytes
    attributes: Dict[int, bytes]
    
    # STUN 消息类型
    BINDING_REQUEST = 0x0001
    BINDING_RESPONSE = 0x0101
    BINDING_ERROR_RESPONSE = 0x0111
    
    # STUN 属性类型
    MAPPED_ADDRESS = 0x0001
    XOR_MAPPED_ADDRESS = 0x0020
    ERROR_CODE = 0x0009
    SOFTWARE = 0x8022
    FINGERPRINT = 0x8028
    
    # STUN Magic Cookie
    MAGIC_COOKIE = 0x2112A442
    
    @classmethod
    def create_binding_request(cls) -> 'StunMessage':
        """创建 STUN Binding 请求"""
        transaction_id = random.randbytes(12)
        return cls(
            message_type=cls.BINDING_REQUEST,
            message_length=0,
            magic_cookie=cls.MAGIC_COOKIE,
            transaction_id=transaction_id,
            attributes={}
        )
    
    def pack(self) -> bytes:
        """将 STUN 消息打包为字节"""
        # 计算消息长度
        attributes_length = sum(len(value) + 4 for value in self.attributes.values())
        
        # 打包头部
        header = struct.pack(
            ">HHI12s",
            self.message_type,
            attributes_length,
            self.magic_cookie,
            self.transaction_id
        )
        
        # 打包属性
        attributes = b""
        for attr_type, attr_value in self.attributes.items():
            attr_len = len(attr_value)
            # 属性头部：类型(2字节) + 长度(2字节)
            attr_header = struct.pack(">HH", attr_type, attr_len)
            # 添加填充以确保4字节对齐
            padding_len = (4 - (attr_len % 4)) % 4
            padding = b"\x00" * padding_len
            attributes += attr_header + attr_value + padding
            
        return header + attributes
    
    @classmethod
    def unpack(cls, data: bytes) -> Optional['StunMessage']:
        """从字节解包 STUN 消息"""
        try:
            # 解析头部
            header_format = ">HHI12s"
            header_size = struct.calcsize(header_format)
            
            if len(data) < header_size:
                return None
                
            message_type, message_length, magic_cookie, transaction_id = struct.unpack(
                header_format,
                data[:header_size]
            )
            
            # 验证 Magic Cookie
            if magic_cookie != cls.MAGIC_COOKIE:
                return None
                
            # 解析属性
            attributes = {}
            pos = header_size
            while pos < len(data):
                # 确保有足够的字节读取属性头部
                if pos + 4 > len(data):
                    break
                    
                # 读取属性头部
                attr_type, attr_len = struct.unpack(">HH", data[pos:pos+4])
                pos += 4
                
                # 读取属性值
                if pos + attr_len > len(data):
                    break
                    
                attr_value = data[pos:pos+attr_len]
                attributes[attr_type] = attr_value
                
                # 移动到下一个4字节对齐的位置
                pos += attr_len
                pos += (4 - (attr_len % 4)) % 4
                
            return cls(
                message_type=message_type,
                message_length=message_length,
                magic_cookie=magic_cookie,
                transaction_id=transaction_id,
                attributes=attributes
            )
            
        except Exception as e:
            logging.error(f"解析 STUN 消息失败: {e}")
            return None

class StunClient:
    """STUN 客户端"""
    
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.socket = None
        self.local_addr = None
        
    async def connect(self) -> None:
        """连接到 STUN 服务器"""
        try:
            # 创建 UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setblocking(False)
            
            # 绑定到随机端口
            self.socket.bind(('0.0.0.0', 0))
            self.local_addr = self.socket.getsockname()
            
            logging.info(f"STUN 客户端绑定到 {self.local_addr}")
            
        except Exception as e:
            logging.error(f"连接 STUN 服务器失败: {e}")
            raise
            
    async def get_binding(self) -> Optional[Dict[str, Any]]:
        """获取 STUN 绑定信息"""
        try:
            # 创建 Binding 请求
            request = StunMessage.create_binding_request()
            request_data = request.pack()
            
            # 发送请求
            await self._send(request_data)
            
            # 接收响应
            response_data = await self._receive()
            if not response_data:
                return None
                
            # 解析响应
            response = StunMessage.unpack(response_data)
            if not response:
                return None
                
            # 检查响应类型
            if response.message_type != StunMessage.BINDING_RESPONSE:
                return None
                
            # 解析映射地址
            mapped_address = self._parse_mapped_address(response)
            if not mapped_address:
                return None
                
            return {
                "local_address": self.local_addr,
                "mapped_address": mapped_address,
                "server": (self.host, self.port)
            }
            
        except Exception as e:
            logging.error(f"获取 STUN 绑定失败: {e}")
            return None
            
    async def _send(self, data: bytes) -> None:
        """发送数据到 STUN 服务器"""
        loop = asyncio.get_event_loop()
        await loop.sock_sendto(self.socket, data, (self.host, self.port))
        
    async def _receive(self, timeout: float = 2.0) -> Optional[bytes]:
        """从 STUN 服务器接收数据"""
        try:
            loop = asyncio.get_event_loop()
            logging.info(f"等待 STUN 响应，超时时间: {timeout}秒")
            data, addr = await asyncio.wait_for(
                loop.sock_recvfrom(self.socket, 2048),
                timeout
            )
            logging.info(f"收到来自 {addr} 的响应")
            return data
        except asyncio.TimeoutError:
            logging.warning(f"接收 STUN 响应超时 ({timeout}秒)")
            return None
        except Exception as e:
            logging.error(f"接收 STUN 响应失败: {str(e)}", exc_info=True)
            return None
            
    def _parse_mapped_address(self, message: StunMessage) -> Optional[Tuple[str, int]]:
        """解析 STUN 响应中的映射地址"""
        try:
            # 首选 XOR-MAPPED-ADDRESS
            if StunMessage.XOR_MAPPED_ADDRESS in message.attributes:
                return self._parse_xor_mapped_address(
                    message.attributes[StunMessage.XOR_MAPPED_ADDRESS],
                    message.magic_cookie
                )
            # 其次使用 MAPPED-ADDRESS
            elif StunMessage.MAPPED_ADDRESS in message.attributes:
                return self._parse_address(
                    message.attributes[StunMessage.MAPPED_ADDRESS]
                )
            return None
        except Exception as e:
            logging.error(f"解析映射地址失败: {e}")
            return None
            
    def _parse_xor_mapped_address(self, data: bytes, magic_cookie: int) -> Optional[Tuple[str, int]]:
        """解析 XOR-MAPPED-ADDRESS 属性"""
        try:
            family = struct.unpack_from(">H", data, 0)[0]
            if family != 0x0001:  # IPv4
                return None
                
            port = struct.unpack_from(">H", data, 2)[0] ^ (magic_cookie >> 16)
            addr = struct.unpack_from(">I", data, 4)[0] ^ magic_cookie
            
            return (
                socket.inet_ntoa(struct.pack(">I", addr)),
                port
            )
        except Exception as e:
            logging.error(f"解析 XOR-MAPPED-ADDRESS 失败: {e}")
            return None
            
    def _parse_address(self, data: bytes) -> Optional[Tuple[str, int]]:
        """解析 MAPPED-ADDRESS 属性"""
        try:
            family = struct.unpack_from(">H", data, 0)[0]
            if family != 0x0001:  # IPv4
                return None
                
            port = struct.unpack_from(">H", data, 2)[0]
            addr = socket.inet_ntoa(data[4:8])
            
            return (addr, port)
        except Exception as e:
            logging.error(f"解析 MAPPED-ADDRESS 失败: {e}")
            return None
            
    async def close(self) -> None:
        """关闭 STUN 客户端"""
        if self.socket:
            self.socket.close()
            self.socket = None 