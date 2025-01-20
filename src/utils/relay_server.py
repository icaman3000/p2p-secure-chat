import asyncio
import logging
import json
import websockets
from typing import Dict, Set, Optional
from dataclasses import dataclass, field
import hmac
import hashlib
import time

@dataclass
class PeerConnection:
    """对等连接信息"""
    peer_id: str
    websocket: websockets.WebSocketServerProtocol
    connected_peers: Set[str] = field(default_factory=set)
    last_heartbeat: float = field(default_factory=time.time)

class RelayServer:
    """中继服务器"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080, secret_key: str = ""):
        self.host = host
        self.port = port
        self.secret_key = secret_key
        self.peers: Dict[str, PeerConnection] = {}
        self.server = None
        
    async def start(self):
        """启动服务器"""
        try:
            self.server = await websockets.serve(
                self._handle_connection,
                self.host,
                self.port
            )
            logging.info(f"中继服务器启动在 {self.host}:{self.port}")
            
            # 启动心跳检查
            asyncio.create_task(self._check_heartbeats())
            
        except Exception as e:
            logging.error(f"启动中继服务器失败: {e}")
            raise
            
    async def stop(self):
        """停止服务器"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
            
    def _generate_token(self, peer_id: str, timestamp: int) -> str:
        """生成认证令牌"""
        if not self.secret_key:
            return ""
            
        message = f"{peer_id}:{timestamp}"
        return hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
    def _verify_token(self, peer_id: str, timestamp: int, token: str) -> bool:
        """验证认证令牌"""
        if not self.secret_key:
            return True
            
        expected_token = self._generate_token(peer_id, timestamp)
        return hmac.compare_digest(token, expected_token)
        
    async def _handle_connection(self, websocket: websockets.WebSocketServerProtocol):
        """处理新的 WebSocket 连接"""
        peer_id = None
        try:
            # 等待认证消息
            auth_msg = await websocket.recv()
            auth_data = json.loads(auth_msg)
            
            # 验证消息格式
            if not all(k in auth_data for k in ["peer_id", "timestamp", "token"]):
                await websocket.close(1002, "认证消息格式错误")
                return
                
            peer_id = auth_data["peer_id"]
            timestamp = auth_data["timestamp"]
            token = auth_data["token"]
            
            # 验证令牌
            if not self._verify_token(peer_id, timestamp, token):
                await websocket.close(1002, "认证失败")
                return
                
            # 检查是否已存在同 ID 的连接
            if peer_id in self.peers:
                await websocket.close(1002, "ID 已被使用")
                return
                
            # 创建连接对象
            connection = PeerConnection(peer_id, websocket)
            self.peers[peer_id] = connection
            
            logging.info(f"对等端 {peer_id} 已连接")
            
            try:
                await self._handle_messages(connection)
            finally:
                # 清理连接
                if peer_id in self.peers:
                    await self._handle_disconnect(connection)
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logging.error(f"处理连接 {peer_id} 时出错: {e}")
            if websocket.open:
                await websocket.close(1011, "内部错误")
                
    async def _handle_messages(self, connection: PeerConnection):
        """处理来自对等端的消息"""
        while True:
            try:
                message = await connection.websocket.recv()
                data = json.loads(message)
                
                # 更新心跳时间
                connection.last_heartbeat = time.time()
                
                # 处理不同类型的消息
                msg_type = data.get("type")
                if msg_type == "heartbeat":
                    await self._handle_heartbeat(connection)
                elif msg_type == "connect":
                    await self._handle_connect_request(connection, data)
                elif msg_type == "disconnect":
                    await self._handle_disconnect_request(connection, data)
                elif msg_type == "data":
                    await self._handle_data(connection, data)
                else:
                    logging.warning(f"未知消息类型: {msg_type}")
                    
            except websockets.exceptions.ConnectionClosed:
                break
            except json.JSONDecodeError:
                logging.warning(f"无效的 JSON 消息")
                continue
            except Exception as e:
                logging.error(f"处理消息时出错: {e}")
                continue
                
    async def _handle_heartbeat(self, connection: PeerConnection):
        """处理心跳消息"""
        try:
            await connection.websocket.send(json.dumps({
                "type": "heartbeat",
                "timestamp": int(time.time())
            }))
        except Exception as e:
            logging.error(f"发送心跳响应失败: {e}")
            
    async def _handle_connect_request(self, connection: PeerConnection, data: dict):
        """处理连接请求"""
        try:
            target_id = data.get("target_id")
            if not target_id:
                return
                
            # 检查目标对等端是否存在
            target = self.peers.get(target_id)
            if not target:
                await connection.websocket.send(json.dumps({
                    "type": "connect_response",
                    "target_id": target_id,
                    "success": False,
                    "error": "目标对等端不存在"
                }))
                return
                
            # 添加到已连接列表
            connection.connected_peers.add(target_id)
            target.connected_peers.add(connection.peer_id)
            
            # 通知双方连接成功
            await connection.websocket.send(json.dumps({
                "type": "connect_response",
                "target_id": target_id,
                "success": True
            }))
            
            await target.websocket.send(json.dumps({
                "type": "peer_connected",
                "peer_id": connection.peer_id
            }))
            
        except Exception as e:
            logging.error(f"处理连接请求失败: {e}")
            
    async def _handle_disconnect_request(self, connection: PeerConnection, data: dict):
        """处理断开连接请求"""
        try:
            target_id = data.get("target_id")
            if not target_id:
                return
                
            # 检查目标对等端是否存在
            target = self.peers.get(target_id)
            if target and target_id in connection.connected_peers:
                # 从已连接列表中移除
                connection.connected_peers.remove(target_id)
                target.connected_peers.remove(connection.peer_id)
                
                # 通知目标对等端
                await target.websocket.send(json.dumps({
                    "type": "peer_disconnected",
                    "peer_id": connection.peer_id
                }))
                
        except Exception as e:
            logging.error(f"处理断开连接请求失败: {e}")
            
    async def _handle_data(self, connection: PeerConnection, data: dict):
        """处理数据转发"""
        try:
            target_id = data.get("target_id")
            payload = data.get("data")
            if not target_id or payload is None:
                return
                
            # 检查是否已连接到目标对等端
            if target_id not in connection.connected_peers:
                logging.warning(f"尝试发送数据到未连接的对等端 {target_id}")
                return
                
            # 获取目标对等端
            target = self.peers.get(target_id)
            if not target:
                logging.warning(f"目标对等端 {target_id} 不存在")
                return
                
            # 转发数据
            await target.websocket.send(json.dumps({
                "type": "data",
                "peer_id": connection.peer_id,
                "data": payload
            }))
            
        except Exception as e:
            logging.error(f"处理数据转发失败: {e}")
            
    async def _handle_disconnect(self, connection: PeerConnection):
        """处理对等端断开连接"""
        try:
            # 通知所有已连接的对等端
            for peer_id in connection.connected_peers:
                peer = self.peers.get(peer_id)
                if peer:
                    peer.connected_peers.remove(connection.peer_id)
                    await peer.websocket.send(json.dumps({
                        "type": "peer_disconnected",
                        "peer_id": connection.peer_id
                    }))
                    
            # 移除连接
            del self.peers[connection.peer_id]
            logging.info(f"对等端 {connection.peer_id} 已断开连接")
            
        except Exception as e:
            logging.error(f"处理断开连接失败: {e}")
            
    async def _check_heartbeats(self):
        """检查心跳超时"""
        while True:
            try:
                current_time = time.time()
                timeout_peers = []
                
                # 检查所有连接
                for peer_id, connection in self.peers.items():
                    if current_time - connection.last_heartbeat > 30:  # 30 秒超时
                        timeout_peers.append(connection)
                        
                # 断开超时的连接
                for connection in timeout_peers:
                    logging.warning(f"对等端 {connection.peer_id} 心跳超时")
                    await connection.websocket.close(1001, "心跳超时")
                    
                await asyncio.sleep(5)  # 每 5 秒检查一次
                
            except Exception as e:
                logging.error(f"检查心跳时出错: {e}")
                await asyncio.sleep(5)  # 发生错误时等待后重试 