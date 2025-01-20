import asyncio
import logging
import json
import time
from utils.connection_manager import ConnectionManager
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class P2PTest:
    """P2P 连接测试程序"""
    
    def __init__(self):
        self.manager1 = None  # 第一个节点
        self.manager2 = None  # 第二个节点
        self.msg_received = asyncio.Event()  # 消息接收事件
        self.received_messages = []  # 接收到的消息列表
        self.test_timeout = 10.0  # 测试超时时间（秒）
        self.concurrent_msg_count = 10  # 并发消息数量
        self.message_events = {}  # 用于跟踪并发消息的事件
        
    async def setup(self):
        """设置测试环境"""
        # 初始化事件和消息列表
        self.msg_received = asyncio.Event()
        self.received_messages = []
        
        # 创建两个连接管理器实例
        self.manager1 = ConnectionManager()
        self.manager2 = ConnectionManager()
        
        # 设置消息处理器
        self.manager1.set_message_handler(self._handle_message)
        self.manager2.set_message_handler(self._handle_message)
        
        # 启动管理器
        await self.manager1.start()
        await self.manager2.start()
        
        logging.info(f"节点1启动在端口: {self.manager1.local_port}")
        logging.info(f"节点2启动在端口: {self.manager2.local_port}")
        
    async def _handle_message(self, peer_id: str, message: dict):
        """处理接收到的消息"""
        logging.info(f"收到来自 {peer_id} 的消息: {json.dumps(message, ensure_ascii=False)}")
        
        # 记录消息
        self.received_messages.append({
            "peer_id": peer_id,
            "content": message,
            "timestamp": time.time()
        })
        
        # 处理并发测试消息
        if "msg_id" in message and message["msg_id"].startswith("concurrent_"):
            msg_id = message["msg_id"]
            if msg_id in self.message_events:
                msg_data = self.message_events[msg_id]
                
                if message["type"] == "test":
                    msg_data["receive_time"] = time.time()
                    # 发送回复
                    if "auto_reply" in message:
                        reply = {
                            "type": "test_reply",
                            "content": f"Reply to: {message['content']}",
                            "timestamp": time.time(),
                            "msg_id": msg_id
                        }
                        if peer_id.startswith("node"):
                            await self.manager2.send_message("node1", reply)
                        else:
                            await self.manager1.send_message("local_test", reply)
                elif message["type"] == "test_reply":
                    msg_data["reply_time"] = time.time()
                    msg_data["event"].set()  # 只在收到回复时设置事件
                    
        # 处理其他类型的消息
        elif message.get("type") == "test" and "auto_reply" in message:
            reply = {
                "type": "test_reply",
                "content": f"Reply to: {message['content']}",
                "timestamp": time.time()
            }
            if peer_id.startswith("node"):
                await self.manager2.send_message("node1", reply)
            else:
                await self.manager1.send_message("local_test", reply)
        
        # 设置消息接收事件
        self.msg_received.set()
        
    async def test_connection(self):
        """测试连接"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "local_test": False,
            "stun_test": False,
            "message_test": False,
            "connection_info": {}
        }
        
        try:
            # 获取两个节点的连接信息
            info1 = self.manager1.get_connection_info()
            info2 = self.manager2.get_connection_info()
            
            results["connection_info"] = {
                "node1": {
                    "local_port": info1["local_port"],
                    "stun_results": info1["stun_results"]
                },
                "node2": {
                    "local_port": info2["local_port"],
                    "stun_results": info2["stun_results"]
                }
            }
            
            # 1. 测试本地连接
            local_addr = ("127.0.0.1", self.manager2.local_port)
            local_success = await self.manager1.connect_to_peer("local_test", local_addr)
            results["local_test"] = local_success
            logging.info(f"本地连接测试: {'成功' if local_success else '失败'}")
            
            # 2. 测试 STUN 辅助连接
            if info2["stun_results"]:
                stun_addr = info2["stun_results"][0]["mapped_address"]
                stun_success = await self.manager1.connect_to_peer("stun_test", stun_addr)
                results["stun_test"] = stun_success
                logging.info(f"STUN 连接测试: {'成功' if stun_success else '失败'}")
                
            # 3. 测试消息传输
            if local_success:
                msg_results = await self.test_message_transmission()
                results["message_test"] = msg_results
            
            return results
            
        except Exception as e:
            logging.error(f"测试过程出错: {e}")
            results["error"] = str(e)
            return results
            
    async def test_message_transmission(self) -> dict:
        """测试消息传输"""
        results = {
            "success": False,
            "tests": {
                "basic": {"success": False, "rtt": None},
                "large_text": {"success": False, "rtt": None},
                "special_chars": {"success": False, "rtt": None},
                "concurrent": {"success": False, "rtt": None, "success_rate": 0},
                "unicode": {"success": False, "rtt": None}
            }
        }
        
        try:
            # 1. 身份验证部分保持不变
            auth_msg1 = {
                "type": "auth",
                "peer_id": "local_test",
                "timestamp": time.time()
            }
            if not await self.manager1.send_message("local_test", auth_msg1):
                logging.error("节点1发送身份验证消息失败")
                return results
                
            await asyncio.sleep(0.5)
            
            node1_addr = ("127.0.0.1", self.manager1.local_port)
            if not await self.manager2.connect_to_peer("node1", node1_addr):
                logging.error("节点2连接到节点1失败")
                return results
                
            auth_msg2 = {
                "type": "auth",
                "peer_id": "node1",
                "timestamp": time.time()
            }
            if not await self.manager2.send_message("node1", auth_msg2):
                logging.error("节点2发送身份验证消息失败")
                return results
                
            await asyncio.sleep(0.5)
            
            # 2. 基本消息测试
            results["tests"]["basic"] = await self._test_basic_message()
            
            # 3. 大文本消息测试
            results["tests"]["large_text"] = await self._test_large_message()
            
            # 4. 特殊字符消息测试
            results["tests"]["special_chars"] = await self._test_special_chars()
            
            # 5. 并发消息测试
            results["tests"]["concurrent"] = await self._test_concurrent_messages()
            
            # 6. Unicode 消息测试
            results["tests"]["unicode"] = await self._test_unicode_message()
            
            # 计算总体成功率
            success_count = sum(1 for test in results["tests"].values() if test["success"])
            results["success"] = success_count == len(results["tests"])
            
            return results
            
        except Exception as e:
            logging.error(f"消息传输测试失败: {e}")
            return results
            
    async def _test_basic_message(self) -> dict:
        """测试基本消息传输"""
        result = {"success": False, "rtt": None}
        
        try:
            self.msg_received.clear()
            self.received_messages.clear()
            
            test_msg = {
                "type": "test",
                "content": "Hello from node 1!",
                "timestamp": time.time(),
                "auto_reply": True
            }
            
            start_time = time.time()
            if not await self.manager1.send_message("local_test", test_msg):
                return result
                
            try:
                for _ in range(2):
                    await asyncio.wait_for(self.msg_received.wait(), timeout=self.test_timeout)
                    self.msg_received.clear()
                    
                if len(self.received_messages) >= 2:
                    result["success"] = True
                    result["rtt"] = (time.time() - start_time) * 1000
                    
            except asyncio.TimeoutError:
                logging.error("基本消息测试超时")
                
        except Exception as e:
            logging.error(f"基本消息测试失败: {e}")
            
        return result
        
    async def _test_large_message(self) -> dict:
        """测试大文本消息传输"""
        result = {"success": False, "rtt": None}
        
        try:
            self.msg_received.clear()
            self.received_messages.clear()
            
            # 生成大约100KB的文本
            large_content = "Large message test " * 5000
            test_msg = {
                "type": "test",
                "content": large_content,
                "timestamp": time.time(),
                "auto_reply": True
            }
            
            start_time = time.time()
            if not await self.manager1.send_message("local_test", test_msg):
                return result
                
            try:
                for _ in range(2):
                    await asyncio.wait_for(self.msg_received.wait(), timeout=self.test_timeout)
                    self.msg_received.clear()
                    
                if len(self.received_messages) >= 2:
                    result["success"] = True
                    result["rtt"] = (time.time() - start_time) * 1000
                    
            except asyncio.TimeoutError:
                logging.error("大文本消息测试超时")
                
        except Exception as e:
            logging.error(f"大文本消息测试失败: {e}")
            
        return result
        
    async def _test_special_chars(self) -> dict:
        """测试特殊字符消息传输"""
        result = {"success": False, "rtt": None}
        
        try:
            self.msg_received.clear()
            self.received_messages.clear()
            
            special_content = """!@#$%^&*()_+-=[]{}|;:'",.<>?`~\n\t\r"""
            test_msg = {
                "type": "test",
                "content": special_content,
                "timestamp": time.time(),
                "auto_reply": True
            }
            
            start_time = time.time()
            if not await self.manager1.send_message("local_test", test_msg):
                return result
                
            try:
                for _ in range(2):
                    await asyncio.wait_for(self.msg_received.wait(), timeout=self.test_timeout)
                    self.msg_received.clear()
                    
                if len(self.received_messages) >= 2:
                    result["success"] = True
                    result["rtt"] = (time.time() - start_time) * 1000
                    
            except asyncio.TimeoutError:
                logging.error("特殊字符消息测试超时")
                
        except Exception as e:
            logging.error(f"特殊字符消息测试失败: {e}")
            
        return result
        
    async def _test_concurrent_messages(self) -> dict:
        """测试并发消息传输"""
        result = {"success": False, "rtt": None, "success_rate": 0}
        
        try:
            self.msg_received.clear()
            self.received_messages.clear()
            self.message_events = {}  # 重置消息事件字典
            
            start_time = time.time()
            tasks = []
            
            # 为每个消息创建独立的事件和计数器
            for i in range(self.concurrent_msg_count):
                msg_id = f"concurrent_{i}"
                self.message_events[msg_id] = {
                    "event": asyncio.Event(),
                    "send_time": None,
                    "receive_time": None,
                    "reply_time": None
                }
                
                test_msg = {
                    "type": "test",
                    "content": f"Concurrent message {i}",
                    "timestamp": time.time(),
                    "auto_reply": True,
                    "msg_id": msg_id
                }
                
                # 记录发送时间
                self.message_events[msg_id]["send_time"] = time.time()
                tasks.append(self.manager1.send_message("local_test", test_msg))
            
            # 等待所有消息发送完成
            send_results = await asyncio.gather(*tasks, return_exceptions=True)
            successful_sends = sum(1 for r in send_results if r)
            
            if successful_sends == 0:
                logging.error("没有消息发送成功")
                return result
            
            # 等待接收消息和回复
            try:
                timeout = self.test_timeout * 2  # 使用两倍超时时间
                wait_tasks = []
                
                async def wait_for_message_completion(msg_id):
                    try:
                        await asyncio.wait_for(self.message_events[msg_id]["event"].wait(), timeout)
                        return True
                    except asyncio.TimeoutError:
                        logging.error(f"消息 {msg_id} 等待超时")
                        return False
                
                # 为每个已发送的消息创建等待任务
                for msg_id in self.message_events:
                    if self.message_events[msg_id]["send_time"] is not None:
                        wait_tasks.append(wait_for_message_completion(msg_id))
                
                # 等待所有消息完成或超时
                wait_results = await asyncio.gather(*wait_tasks)
                completed_count = sum(1 for r in wait_results if r)
                
                # 计算成功率和往返时间
                if successful_sends > 0:
                    result["success_rate"] = (completed_count / successful_sends) * 100
                    result["success"] = completed_count == successful_sends
                    
                    # 计算平均往返时间
                    rtts = []
                    for msg_id, msg_data in self.message_events.items():
                        if msg_data["send_time"] and msg_data["reply_time"]:
                            rtts.append((msg_data["reply_time"] - msg_data["send_time"]) * 1000)
                    
                    if rtts:
                        result["rtt"] = sum(rtts) / len(rtts)
                
            except Exception as e:
                logging.error(f"等待并发消息完成时出错: {e}")
                
        except Exception as e:
            logging.error(f"并发消息测试失败: {e}")
            
        return result
        
    async def _test_unicode_message(self) -> dict:
        """测试 Unicode 消息传输"""
        result = {"success": False, "rtt": None}
        
        try:
            self.msg_received.clear()
            self.received_messages.clear()
            
            unicode_content = """
            🌟 Unicode Test 测试 유니코드 テスト
            😀 😎 🤔 🚀 💻 🌍
            안녕하세요 こんにちは 你好
            """
            test_msg = {
                "type": "test",
                "content": unicode_content,
                "timestamp": time.time(),
                "auto_reply": True
            }
            
            start_time = time.time()
            if not await self.manager1.send_message("local_test", test_msg):
                return result
                
            try:
                for _ in range(2):
                    await asyncio.wait_for(self.msg_received.wait(), timeout=self.test_timeout)
                    self.msg_received.clear()
                    
                if len(self.received_messages) >= 2:
                    result["success"] = True
                    result["rtt"] = (time.time() - start_time) * 1000
                    
            except asyncio.TimeoutError:
                logging.error("Unicode 消息测试超时")
                
        except Exception as e:
            logging.error(f"Unicode 消息测试失败: {e}")
            
        return result
        
    async def cleanup(self):
        """清理测试环境"""
        if self.manager1:
            await self.manager1.stop()
        if self.manager2:
            await self.manager2.stop()
            
    def print_results(self, results: dict):
        """打印测试结果"""
        print("\n=== P2P 连接测试报告 ===")
        print(f"测试时间: {results['timestamp']}\n")
        
        print("1. 连接测试结果:")
        print(f"  - 本地连接测试: {'✅ 成功' if results['local_test'] else '❌ 失败'}")
        print(f"  - STUN 连接测试: {'✅ 成功' if results['stun_test'] else '❌ 失败'}")
        
        if "message_test" in results and isinstance(results["message_test"], dict):
            msg_test = results["message_test"]
            print("\n2. 消息传输测试:")
            print(f"  - 总体状态: {'✅ 成功' if msg_test['success'] else '❌ 失败'}")
            
            for test_name, test_result in msg_test["tests"].items():
                print(f"\n  {test_name.replace('_', ' ').title()}:")
                print(f"    - 状态: {'✅ 成功' if test_result['success'] else '❌ 失败'}")
                if test_result.get("rtt") is not None:
                    print(f"    - 往返时间: {test_result['rtt']:.2f}ms")
                if "success_rate" in test_result:
                    print(f"    - 成功率: {test_result['success_rate']:.1f}%")
        
        print("\n3. 节点1信息:")
        node1_info = results["connection_info"]["node1"]
        print(f"  - 本地端口: {node1_info['local_port']}")
        for i, stun in enumerate(node1_info["stun_results"], 1):
            print(f"  - STUN {i}: {stun['mapped_address']}")
        
        print("\n4. 节点2信息:")
        node2_info = results["connection_info"]["node2"]
        print(f"  - 本地端口: {node2_info['local_port']}")
        for i, stun in enumerate(node2_info["stun_results"], 1):
            print(f"  - STUN {i}: {stun['mapped_address']}")
            
        if "error" in results:
            print(f"\n错误信息: {results['error']}")
            
        print("\n=== 测试报告结束 ===")
            
async def main():
    """主函数"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 创建并运行测试
    tester = P2PTest()
    try:
        # 设置测试环境
        await tester.setup()
        
        # 运行测试
        results = await tester.test_connection()
        
        # 打印结果
        tester.print_results(results)
        
    finally:
        # 清理环境
        await tester.cleanup()
        
if __name__ == "__main__":
    asyncio.run(main()) 