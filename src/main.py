import sys
import asyncio
import logging
import qasync
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from src.ui.main_window import MainWindow
from src.utils.database import init_database
from src.utils.connection_manager import ConnectionManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class P2PChat:
    def __init__(self):
        self.manager = None
        self.received_messages = []
        self.msg_received = asyncio.Event()
        
    async def setup(self):
        """设置P2P连接"""
        try:
            # 创建连接管理器
            self.manager = ConnectionManager()
            
            # 设置消息处理器
            self.manager.set_message_handler(self._handle_message)
            
            # 启动管理器
            await self.manager.start()
            
            logging.info(f"P2P聊天启动在端口: {self.manager.local_port}")
            
        except Exception as e:
            logging.error(f"P2P聊天启动失败: {e}")
            raise
            
    async def _handle_message(self, peer_id: str, message: dict):
        """处理接收到的消息"""
        logging.info(f"收到来自 {peer_id} 的消息: {message}")
        
        # 记录消息
        self.received_messages.append({
            "peer_id": peer_id,
            "content": message,
            "timestamp": asyncio.get_event_loop().time()
        })
        
        # 如果是测试消息且需要回复
        if message.get("type") == "test" and "auto_reply" in message:
            reply = {
                "type": "test_reply",
                "content": f"Reply to: {message['content']}",
                "timestamp": asyncio.get_event_loop().time()
            }
            await self.manager.send_message(peer_id, reply)
            
        # 设置消息接收事件
        self.msg_received.set()
        
    async def connect_to_peer(self, peer_id: str, peer_addr):
        """连接到对等端"""
        try:
            # 尝试连接
            success = await self.manager.connect_to_peer(peer_id, peer_addr)
            if success:
                logging.info(f"成功连接到对等端 {peer_id}")
                return True
            else:
                logging.warning(f"无法连接到对等端 {peer_id}")
                return False
                
        except Exception as e:
            logging.error(f"连接对等端失败: {e}")
            return False
            
    async def cleanup(self):
        """清理资源"""
        if self.manager:
            await self.manager.stop()

def main():
    app = QApplication(sys.argv)
    
    # 创建事件循环
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # 初始化数据库
    init_database(0)
    
    # 创建P2P聊天实例
    p2p_chat = P2PChat()
    
    # 创建并显示主窗口
    window = MainWindow(p2p_chat)
    window.show()
    
    # 启动P2P连接
    asyncio.create_task(p2p_chat.setup())
    
    # 创建定时器以处理异步事件
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(100)
    
    # 运行事件循环
    with loop:
        try:
            loop.run_forever()
        finally:
            # 清理资源
            loop.run_until_complete(p2p_chat.cleanup())

if __name__ == "__main__":
    main() 