import asyncio
import logging
import json
import time
from typing import Optional, Dict, Any
from utils.stun_client import StunClient
from utils.turn_client import TurnClient
from utils.relay_server import RelayServer
import websockets

class NetworkTester:
    """网络功能测试器"""
    
    def __init__(self):
        # STUN 服务器列表
        self.stun_servers = [
            "stun.voip.blackberry.com:3478",
            "stun.stunprotocol.org:3478",
            "stun.voipgate.com:3478",
            "stun.sipgate.net:10000"
        ]
        
        # TURN 服务器列表
        self.turn_servers = [
            {
                "url": "turn:relay.metered.ca:80",
                "username": "openrelayproject",
                "password": "openrelayproject",
                "transport": "tcp"
            }
        ]
        self.relay_server = None
        self.relay_client = None
        
    async def test_stun(self) -> Dict[str, Any]:
        """测试 STUN 功能"""
        results = {
            "success": False,
            "tested_servers": [],
            "working_servers": [],
            "mapped_addresses": []
        }
        
        for server in self.stun_servers:
            try:
                host, port = server.split(":")
                port = int(port)
                
                logging.info(f"测试 STUN 服务器: {server}")
                results["tested_servers"].append(server)
                
                # 创建 STUN 客户端
                client = StunClient(host, port)
                await client.connect()
                
                try:
                    # 获取映射地址
                    binding = await client.get_binding()
                    if binding:
                        results["working_servers"].append(server)
                        results["mapped_addresses"].append(binding)
                        logging.info(f"STUN 绑定成功: {binding}")
                finally:
                    await client.close()
                    
            except Exception as e:
                logging.error(f"测试 STUN 服务器 {server} 失败: {e}")
                
        results["success"] = len(results["working_servers"]) > 0
        return results
        
    async def test_turn(self) -> Dict[str, Any]:
        """测试 TURN 功能"""
        results = {
            "success": False,
            "tested_servers": [],
            "working_servers": [],
            "allocations": []
        }
        
        for server in self.turn_servers:
            try:
                # 解析 TURN URL
                url = server["url"]
                if not url.startswith("turn:"):
                    continue
                    
                host_port = url[5:]  # 移除 "turn:" 前缀
                host, port = host_port.split(":")
                port = int(port)
                transport = server.get("transport", "udp")
                
                logging.info(f"测试 TURN 服务器: {url} (transport={transport})")
                results["tested_servers"].append(url)
                
                # 创建 TURN 客户端
                client = TurnClient(
                    host=host,
                    port=port,
                    username=server["username"],
                    password=server["password"]
                )
                
                try:
                    # 连接到服务器
                    logging.info(f"正在连接到 TURN 服务器 {host}:{port}...")
                    await client.connect()
                    logging.info("TURN 服务器连接成功")
                    
                    # 尝试分配
                    logging.info("正在请求 TURN 分配...")
                    allocation = await client.allocate()
                    if allocation:
                        results["working_servers"].append(url)
                        results["allocations"].append(allocation)
                        logging.info(f"TURN 分配成功: {allocation}")
                    else:
                        logging.error("TURN 分配失败: 未收到分配响应")
                finally:
                    await client.close()
                    
            except Exception as e:
                logging.error(f"测试 TURN 服务器 {url} 失败: {str(e)}", exc_info=True)
                
        results["success"] = len(results["working_servers"]) > 0
        return results
        
    async def test_relay(self) -> Dict[str, Any]:
        """测试中继服务器功能"""
        results = {
            "success": False,
            "server_start": False,
            "client_connect": False,
            "peer_connect": False,
            "data_transfer": False
        }
        
        try:
            # 启动中继服务器
            self.relay_server = RelayServer(
                host="127.0.0.1",
                port=8080,
                secret_key="test_key"
            )
            await self.relay_server.start()
            results["server_start"] = True
            logging.info("中继服务器启动成功")
            
            # 创建两个测试客户端
            client1 = await self._create_relay_client("peer1")
            client2 = await self._create_relay_client("peer2")
            
            if client1 and client2:
                results["client_connect"] = True
                logging.info("测试客户端连接成功")
                
                # 测试对等连接
                success = await self._test_peer_connection(client1, client2)
                results["peer_connect"] = success
                
                if success:
                    # 测试数据传输
                    success = await self._test_data_transfer(client1, client2)
                    results["data_transfer"] = success
                    
            results["success"] = all([
                results["server_start"],
                results["client_connect"],
                results["peer_connect"],
                results["data_transfer"]
            ])
            
        except Exception as e:
            logging.error(f"测试中继服务器失败: {e}")
        finally:
            # 清理资源
            if self.relay_server:
                await self.relay_server.stop()
                
        return results
        
    async def _create_relay_client(self, peer_id: str) -> Optional[websockets.WebSocketClientProtocol]:
        """创建中继客户端连接"""
        try:
            # 连接到中继服务器
            websocket = await websockets.connect("ws://127.0.0.1:8080")
            
            # 生成认证消息
            timestamp = int(time.time())
            auth_msg = {
                "peer_id": peer_id,
                "timestamp": timestamp,
                "token": self._generate_test_token(peer_id, timestamp)
            }
            
            # 发送认证消息
            await websocket.send(json.dumps(auth_msg))
            
            return websocket
            
        except Exception as e:
            logging.error(f"创建中继客户端失败: {e}")
            return None
            
    def _generate_test_token(self, peer_id: str, timestamp: int) -> str:
        """生成测试用的认证令牌"""
        import hmac
        import hashlib
        
        message = f"{peer_id}:{timestamp}"
        return hmac.new(
            "test_key".encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
    async def _test_peer_connection(
        self,
        client1: websockets.WebSocketClientProtocol,
        client2: websockets.WebSocketClientProtocol
    ) -> bool:
        """测试对等连接"""
        try:
            # 发送连接请求
            await client1.send(json.dumps({
                "type": "connect",
                "target_id": "peer2"
            }))
            
            # 等待连接响应
            response = await client1.recv()
            data = json.loads(response)
            
            if data.get("type") == "connect_response" and data.get("success"):
                # 等待对方收到连接通知
                notification = await client2.recv()
                notify_data = json.loads(notification)
                
                return (
                    notify_data.get("type") == "peer_connected" and
                    notify_data.get("peer_id") == "peer1"
                )
                
            return False
            
        except Exception as e:
            logging.error(f"测试对等连接失败: {e}")
            return False
            
    async def _test_data_transfer(
        self,
        client1: websockets.WebSocketClientProtocol,
        client2: websockets.WebSocketClientProtocol
    ) -> bool:
        """测试数据传输"""
        try:
            # 发送测试数据
            test_data = "Hello, peer2!"
            await client1.send(json.dumps({
                "type": "data",
                "target_id": "peer2",
                "data": test_data
            }))
            
            # 等待数据转发
            response = await client2.recv()
            data = json.loads(response)
            
            return (
                data.get("type") == "data" and
                data.get("peer_id") == "peer1" and
                data.get("data") == test_data
            )
            
        except Exception as e:
            logging.error(f"测试数据传输失败: {e}")
            return False
            
async def run_tests():
    """运行所有测试"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    tester = NetworkTester()
    
    # 测试 STUN
    logging.info("=== 开始测试 STUN ===")
    stun_results = await tester.test_stun()
    logging.info(f"STUN 测试结果: {json.dumps(stun_results, indent=2)}")
    
    # 测试 TURN
    logging.info("\n=== 开始测试 TURN ===")
    turn_results = await tester.test_turn()
    logging.info(f"TURN 测试结果: {json.dumps(turn_results, indent=2)}")
    
    # 测试中继服务器
    logging.info("\n=== 开始测试中继服务器 ===")
    relay_results = await tester.test_relay()
    logging.info(f"中继服务器测试结果: {json.dumps(relay_results, indent=2)}")
    
if __name__ == "__main__":
    asyncio.run(run_tests()) 