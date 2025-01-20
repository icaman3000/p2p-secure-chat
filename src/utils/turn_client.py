import asyncio
import logging
import socket
import struct
import hmac
import hashlib
import base64
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
import random

@dataclass
class TurnMessage:
    """TURN 消息结构"""
    message_type: int
    message_length: int
    magic_cookie: int
    transaction_id: bytes
    attributes: Dict[int, bytes]
    
    # TURN 消息类型
    ALLOCATION_REQUEST = 0x0003
    ALLOCATION_RESPONSE = 0x0103
    ALLOCATION_ERROR_RESPONSE = 0x0113
    REFRESH_REQUEST = 0x0004
    REFRESH_RESPONSE = 0x0104
    SEND_INDICATION = 0x0016
    DATA_INDICATION = 0x0017
    CREATE_PERMISSION_REQUEST = 0x0008
    CREATE_PERMISSION_RESPONSE = 0x0108
    
    # TURN 属性类型
    MAPPED_ADDRESS = 0x0001
    XOR_PEER_ADDRESS = 0x0012
    LIFETIME = 0x000D
    XOR_RELAYED_ADDRESS = 0x0016
    DATA = 0x0013
    REQUESTED_TRANSPORT = 0x0019
    REALM = 0x0014
    NONCE = 0x0015
    USERNAME = 0x0006
    MESSAGE_INTEGRITY = 0x0008
    ERROR_CODE = 0x0009
    
    # TURN Magic Cookie (与 STUN 相同)
    MAGIC_COOKIE = 0x2112A442
    
    @classmethod
    def create_allocation_request(cls, username: Optional[str] = None,
                                realm: Optional[str] = None,
                                nonce: Optional[str] = None,
                                password: Optional[str] = None) -> 'TurnMessage':
        """创建分配请求消息"""
        # 生成事务ID
        transaction_id = random.randbytes(12)
        
        # 创建基本消息
        request = cls(
            message_type=cls.ALLOCATION_REQUEST,
            message_length=0,  # 长度将在打包时计算
            magic_cookie=cls.MAGIC_COOKIE,
            transaction_id=transaction_id,
            attributes={}
        )
        
        # 添加请求传输属性 (UDP)
        request.attributes[cls.REQUESTED_TRANSPORT] = struct.pack("!BBBB", 17, 0, 0, 0)
        
        # 如果有认证信息，添加认证属性
        if username and realm and nonce:
            # 添加用户名
            request.attributes[cls.USERNAME] = username.encode('utf-8')
            
            # 添加 realm
            request.attributes[cls.REALM] = realm.encode('utf-8')
            
            # 添加 nonce
            request.attributes[cls.NONCE] = nonce.encode('utf-8')
            
            # 计算消息完整性
            if password:
                key = hashlib.md5(f"{username}:{realm}:{password}"
                                .encode('utf-8')).digest()
                request.add_message_integrity(key)
        
        return request
    
    def add_string_attribute(self, attr_type: int, value: str):
        """添加字符串属性"""
        self.attributes[attr_type] = value.encode('utf-8')
    
    def add_message_integrity(self, key: bytes):
        """添加消息完整性属性"""
        try:
            # 计算消息长度（包括 MESSAGE-INTEGRITY 属性）
            msg_len = self.message_length + 24  # 20 字节 HMAC-SHA1 + 4 字节属性头
            
            # 创建用于计算 HMAC 的消息
            header = struct.pack(
                ">HHI12s",
                self.message_type,
                msg_len,
                self.magic_cookie,
                self.transaction_id
            )
            
            # 添加现有属性
            attributes = b""
            for attr_type, attr_value in sorted(self.attributes.items()):
                if attr_type == self.MESSAGE_INTEGRITY:
                    continue
                attr_len = len(attr_value)
                attr_header = struct.pack(">HH", attr_type, attr_len)
                padding_len = (4 - (attr_len % 4)) % 4
                padding = b"\x00" * padding_len
                attributes += attr_header + attr_value + padding
            
            # 计算 HMAC-SHA1
            message = header + attributes
            hmac_obj = hmac.new(key, message, hashlib.sha1)
            self.attributes[self.MESSAGE_INTEGRITY] = hmac_obj.digest()
            
            logging.debug("已添加消息完整性")
            
        except Exception as e:
            logging.error(f"添加消息完整性失败: {e}")
    
    def pack(self) -> bytes:
        """打包 TURN 消息为字节"""
        try:
            # 计算属性总长度
            total_length = 0
            attr_data = []
            
            for attr_type, value in self.attributes.items():
                # 对齐到 4 字节边界
                padding_len = (4 - (len(value) % 4)) % 4
                padding = b'\x00' * padding_len
                
                # 添加属性头部和数据
                attr_header = struct.pack(">HH", attr_type, len(value))
                attr_data.append(attr_header + value + padding)
                total_length += len(attr_header) + len(value) + padding_len
            
            # 更新消息长度
            self.message_length = total_length
            
            # 打包消息头部
            header = struct.pack(
                ">HHI12s",
                self.message_type,
                self.message_length,
                self.magic_cookie,
                self.transaction_id
            )
            
            # 组合所有数据
            return header + b''.join(attr_data)
            
        except Exception as e:
            logging.error(f"打包 TURN 消息失败: {e}")
            return b''
    
    @classmethod
    def unpack(cls, data: bytes) -> Optional['TurnMessage']:
        """从字节解包 TURN 消息"""
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
                if pos + 4 > len(data):
                    break
                    
                attr_type, attr_len = struct.unpack(">HH", data[pos:pos+4])
                pos += 4
                
                if pos + attr_len > len(data):
                    break
                    
                attr_value = data[pos:pos+attr_len]
                attributes[attr_type] = attr_value
                
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
            logging.error(f"解析 TURN 消息失败: {e}")
            return None
    
    def get_attribute(self, attr_type: int) -> Optional[bytes]:
        """获取属性值"""
        return self.attributes.get(attr_type)
        
    def get_error_code(self) -> Tuple[int, str]:
        """获取错误代码和原因"""
        try:
            if self.ERROR_CODE in self.attributes:
                data = self.attributes[self.ERROR_CODE]
                if len(data) >= 4:
                    error_class = data[2] & 0x07
                    error_number = data[3]
                    error_code = error_class * 100 + error_number
                    
                    reason = ""
                    if len(data) > 4:
                        reason = data[4:].decode('utf-8')
                    return error_code, reason
            return 0, ""
        except Exception as e:
            logging.error(f"解析错误代码失败: {e}")
            return 0, str(e)

class TurnClient:
    """TURN 客户端"""
    
    def __init__(self, host: str, port: int, username: str = None, password: str = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.socket = None
        self.local_addr = None
        self.realm = None
        self.nonce = None
        self.is_tcp = port == 443  # 对 443 端口使用 TCP
        self.relayed_addr = None
        self.permissions = set()
        
    async def connect(self) -> None:
        """连接到 TURN 服务器"""
        try:
            # 根据端口选择 TCP 或 UDP
            if self.is_tcp:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.setblocking(False)
                
                # 连接到服务器
                loop = asyncio.get_event_loop()
                try:
                    await loop.sock_connect(self.socket, (self.host, self.port))
                    logging.info(f"TCP 连接到 TURN 服务器成功")
                except Exception as e:
                    logging.error(f"TCP 连接失败: {e}")
                    raise
            else:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.socket.setblocking(False)
            
            # 绑定到随机端口
            if not self.is_tcp:  # TCP 不需要绑定
                self.socket.bind(('0.0.0.0', 0))
                self.local_addr = self.socket.getsockname()
                logging.info(f"TURN 客户端绑定到 {self.local_addr}")
            
            # 添加认证信息
            if self.username and self.password:
                logging.info("开始 TURN 认证流程")
                
                # 首次请求获取 realm 和 nonce (不带认证)
                request = TurnMessage.create_allocation_request()
                await self._send(request.pack())
                
                response = await self._receive(timeout=5.0)
                if not response:
                    raise Exception("未收到 TURN 服务器响应")
                    
                response_msg = TurnMessage.unpack(response)
                if not response_msg:
                    raise Exception("无法解析 TURN 响应")
                    
                if response_msg.message_type == TurnMessage.ALLOCATION_ERROR_RESPONSE:
                    self.realm = response_msg.get_attribute(TurnMessage.REALM)
                    self.nonce = response_msg.get_attribute(TurnMessage.NONCE)
                    
                    if not self.realm or not self.nonce:
                        error_code, reason = response_msg.get_error_code()
                        raise Exception(f"未收到完整的认证参数 (错误 {error_code}: {reason})")
                        
                    logging.info("获取到 TURN 认证参数")
                    
                    # 使用完整认证重新发送请求
                    request = TurnMessage.create_allocation_request(
                        username=self.username,
                        realm=self.realm.decode('utf-8'),
                        nonce=self.nonce.decode('utf-8'),
                        password=self.password
                    )
                    await self._send(request.pack())
                    
                    # 等待分配响应
                    response = await self._receive(timeout=5.0)
                    if not response:
                        raise Exception("未收到 TURN 分配响应")
                        
                    response_msg = TurnMessage.unpack(response)
                    if not response_msg:
                        raise Exception("无法解析 TURN 响应")
                        
                    if response_msg.message_type != TurnMessage.ALLOCATION_RESPONSE:
                        error_code, reason = response_msg.get_error_code()
                        raise Exception(f"TURN 分配失败 (错误 {error_code}: {reason})")
                        
                    # 解析中继地址
                    self.relayed_addr = self._parse_relayed_address(response_msg)
                    if not self.relayed_addr:
                        raise Exception("未收到中继地址")
                        
                    logging.info(f"TURN 认证成功，中继地址: {self.relayed_addr}")
                    return
                    
            raise Exception("TURN 认证失败")
            
        except Exception as e:
            logging.error(f"连接 TURN 服务器失败: {e}")
            if self.socket:
                self.socket.close()
            raise
            
    async def allocate(self) -> Optional[Dict[str, Any]]:
        """申请 TURN 分配"""
        try:
            if not self.realm or not self.nonce:
                logging.error("缺少认证参数")
                return None
                
            # 创建认证密钥
            key = self._create_auth_key()
            
            # 创建分配请求
            request = TurnMessage.create_allocation_request(
                self.username,
                self.realm,
                self.nonce,
                key
            )
            
            # 发送请求
            await self._send(request.pack())
            
            # 接收响应
            response_data = await self._receive()
            if not response_data:
                return None
                
            # 解析响应
            response = TurnMessage.unpack(response_data)
            if not response:
                return None
                
            # 检查响应类型
            if response.message_type == TurnMessage.ALLOCATION_RESPONSE:
                # 解析中继地址
                relayed_addr = self._parse_relayed_address(response)
                if relayed_addr:
                    self.relayed_addr = relayed_addr
                    return {
                        "local_address": self.local_addr,
                        "relayed_address": relayed_addr,
                        "server": (self.host, self.port)
                    }
                    
            elif response.message_type == TurnMessage.ALLOCATION_ERROR_RESPONSE:
                error_code, reason = response.get_error_code()
                logging.error(f"分配失败: 错误 {error_code}: {reason}")
                
            return None
            
        except Exception as e:
            logging.error(f"TURN 分配失败: {e}")
            return None
            
    async def create_permission(self, peer_addr: Tuple[str, int]) -> bool:
        """创建发送权限"""
        try:
            if not self.relayed_addr:
                logging.error("未分配中继地址")
                return False
                
            # 创建权限请求
            request = self._create_permission_request(peer_addr[0])
            
            # 发送请求
            await self._send(request.pack())
            
            # 接收响应
            response_data = await self._receive()
            if not response_data:
                return False
                
            # 解析响应
            response = TurnMessage.unpack(response_data)
            if not response:
                return False
                
            # 检查响应类型
            if response.message_type == TurnMessage.CREATE_PERMISSION_RESPONSE:
                self.permissions.add(peer_addr[0])
                return True
                
            return False
            
        except Exception as e:
            logging.error(f"创建权限失败: {e}")
            return False
            
    async def send_data(self, data: bytes, peer_addr: Tuple[str, int]) -> bool:
        """发送数据到对等端"""
        try:
            if not self.relayed_addr:
                logging.error("未分配中继地址")
                return False
                
            if peer_addr[0] not in self.permissions:
                logging.error("未获得发送权限")
                return False
                
            # 创建发送指示
            indication = self._create_send_indication(data, peer_addr)
            
            # 发送数据
            await self._send(indication.pack())
            return True
            
        except Exception as e:
            logging.error(f"发送数据失败: {e}")
            return False
            
    async def _get_auth_params(self) -> None:
        """获取认证参数"""
        try:
            # 创建初始分配请求（不带认证）
            request = TurnMessage(
                message_type=TurnMessage.ALLOCATION_REQUEST,
                message_length=4,
                magic_cookie=TurnMessage.MAGIC_COOKIE,
                transaction_id=random.randbytes(12),
                attributes={
                    TurnMessage.REQUESTED_TRANSPORT: struct.pack(">BBBB", 17, 0, 0, 0)
                }
            )
            
            # 发送请求
            await self._send(request.pack())
            
            # 接收响应
            response_data = await self._receive()
            if not response_data:
                return
                
            # 解析响应
            response = TurnMessage.unpack(response_data)
            if not response:
                return
                
            # 从错误响应中获取 realm 和 nonce
            if response.message_type == TurnMessage.ALLOCATION_ERROR_RESPONSE:
                if TurnMessage.REALM in response.attributes:
                    self.realm = response.attributes[TurnMessage.REALM].decode()
                if TurnMessage.NONCE in response.attributes:
                    self.nonce = response.attributes[TurnMessage.NONCE].decode()
                    
        except Exception as e:
            logging.error(f"获取认证参数失败: {e}")
            
    def _create_auth_key(self) -> bytes:
        """创建认证密钥"""
        try:
            # 使用 MD5 生成长期凭证密钥
            auth_str = f"{self.username}:{self.realm.decode('utf-8')}:{self.password}"
            key = hashlib.md5(auth_str.encode('utf-8')).digest()
            logging.debug("已生成认证密钥")
            return key
        except Exception as e:
            logging.error(f"生成认证密钥失败: {e}")
            raise
        
    def _create_permission_request(self, peer_ip: str) -> TurnMessage:
        """创建权限请求"""
        key = self._create_auth_key()
        request = TurnMessage(
            message_type=TurnMessage.CREATE_PERMISSION_REQUEST,
            message_length=0,
            magic_cookie=TurnMessage.MAGIC_COOKIE,
            transaction_id=random.randbytes(12),
            attributes={}
        )
        
        # 添加对等端地址
        peer_addr = socket.inet_aton(peer_ip)
        port = 0  # 权限只需要 IP
        addr_attr = struct.pack(">HH4s", 0x0001, port, peer_addr)
        request.attributes[TurnMessage.XOR_PEER_ADDRESS] = addr_attr
        
        # 添加认证属性
        request.add_string_attribute(TurnMessage.USERNAME, self.username)
        request.add_string_attribute(TurnMessage.REALM, self.realm)
        request.add_string_attribute(TurnMessage.NONCE, self.nonce)
        request.add_message_integrity(key)
        
        return request
        
    def _create_send_indication(self, data: bytes, peer_addr: Tuple[str, int]) -> TurnMessage:
        """创建发送指示"""
        indication = TurnMessage(
            message_type=TurnMessage.SEND_INDICATION,
            message_length=0,
            magic_cookie=TurnMessage.MAGIC_COOKIE,
            transaction_id=random.randbytes(12),
            attributes={}
        )
        
        # 添加数据
        indication.attributes[TurnMessage.DATA] = data
        
        # 添加对等端地址
        peer_addr_bin = socket.inet_aton(peer_addr[0])
        addr_attr = struct.pack(">HH4s", 0x0001, peer_addr[1], peer_addr_bin)
        indication.attributes[TurnMessage.XOR_PEER_ADDRESS] = addr_attr
        
        return indication
        
    async def _send(self, data: bytes) -> None:
        """发送数据到 TURN 服务器"""
        try:
            loop = asyncio.get_event_loop()
            if self.is_tcp:
                # TCP 需要添加消息长度前缀
                length = len(data)
                length_prefix = struct.pack(">H", length)
                await loop.sock_sendall(self.socket, length_prefix + data)
            else:
                await loop.sock_sendto(self.socket, data, (self.host, self.port))
            logging.debug(f"发送 {len(data)} 字节到 TURN 服务器")
        except Exception as e:
            logging.error(f"发送数据失败: {e}")
            raise
        
    async def _receive(self, timeout: float = 5.0) -> Optional[bytes]:
        """从 TURN 服务器接收数据"""
        try:
            loop = asyncio.get_event_loop()
            logging.info(f"等待 TURN 响应，超时时间: {timeout}秒")
            
            if self.is_tcp:
                # 首先读取 2 字节的长度前缀
                length_data = await asyncio.wait_for(
                    loop.sock_recv(self.socket, 2),
                    timeout
                )
                if not length_data or len(length_data) != 2:
                    raise Exception("无法读取消息长度")
                    
                length = struct.unpack(">H", length_data)[0]
                data = await asyncio.wait_for(
                    loop.sock_recv(self.socket, length),
                    timeout
                )
            else:
                data, addr = await asyncio.wait_for(
                    loop.sock_recvfrom(self.socket, 2048),
                    timeout
                )
                logging.info(f"收到来自 {addr} 的响应")
                
            if data:
                logging.debug(f"收到 {len(data)} 字节的响应")
            return data
            
        except asyncio.TimeoutError:
            logging.warning(f"接收 TURN 响应超时 ({timeout}秒)")
            return None
        except Exception as e:
            logging.error(f"接收 TURN 响应失败: {str(e)}", exc_info=True)
            return None
            
    def _parse_relayed_address(self, message: TurnMessage) -> Optional[Tuple[str, int]]:
        """解析中继地址"""
        try:
            if TurnMessage.XOR_RELAYED_ADDRESS in message.attributes:
                data = message.attributes[TurnMessage.XOR_RELAYED_ADDRESS]
                family = struct.unpack_from(">H", data, 0)[0]
                if family != 0x0001:  # IPv4
                    return None
                    
                port = struct.unpack_from(">H", data, 2)[0] ^ (message.magic_cookie >> 16)
                addr = struct.unpack_from(">I", data, 4)[0] ^ message.magic_cookie
                
                return (
                    socket.inet_ntoa(struct.pack(">I", addr)),
                    port
                )
            return None
        except Exception as e:
            logging.error(f"解析中继地址失败: {e}")
            return None
            
    async def close(self) -> None:
        """关闭 TURN 客户端"""
        if self.socket:
            self.socket.close()
            self.socket = None 