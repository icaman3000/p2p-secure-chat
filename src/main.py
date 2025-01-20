import sys
import asyncio
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QEventLoop
from src.ui.main_window import MainWindow
from src.ui.login_widget import LoginWidget
from src.utils.database import init_database
from src.utils.connection_manager import ConnectionManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class P2PChatApp:
    def __init__(self):
        self.connection_manager = None
        self.app = None
        self.window = None
        self.login_widget = None
        self.loop = None
        self.user_id = None
        self.username = None
        
    async def setup_connection(self, user_id: int, username: str):
        """设置P2P连接"""
        try:
            self.user_id = user_id
            self.username = username
            
            # 初始化数据库
            await self.loop.run_in_executor(None, init_database, user_id)
            
            # 创建连接管理器
            self.connection_manager = ConnectionManager()
            
            # 设置消息处理器
            self.connection_manager.set_message_handler(self._handle_message)
            
            # 启动连接管理器
            await self.connection_manager.start()
            logging.info(f"节点启动在端口: {self.connection_manager.local_port}")
            
            # 获取 STUN 绑定信息
            stun_results = self.connection_manager.stun_results
            if stun_results:
                for result in stun_results:
                    mapped_addr = result.get("mapped_address")
                    if mapped_addr:
                        logging.info(f"STUN映射地址: {mapped_addr}")
            
            return True
            
        except Exception as e:
            logging.error(f"设置连接失败: {e}")
            return False
            
    async def connect_to_peer(self, peer_id: str, peer_addr):
        """连接到对等节点"""
        try:
            success = await self.connection_manager.connect_to_peer(peer_id, peer_addr)
            if success:
                logging.info(f"连接到节点 {peer_id} 成功")
            else:
                logging.error(f"连接到节点 {peer_id} 失败")
            return success
            
        except Exception as e:
            logging.error(f"连接到节点 {peer_id} 时出错: {e}")
            return False
            
    async def _handle_message(self, peer_id: str, message: dict):
        """处理接收到的消息"""
        try:
            logging.info(f"收到来自 {peer_id} 的消息: {message}")
            
            # 如果是认证消息，发送回复
            if message.get("type") == "auth":
                auth_reply = {
                    "type": "auth_reply",
                    "peer_id": self.user_id,
                    "username": self.username,
                    "timestamp": message.get("timestamp")
                }
                await self.connection_manager.send_message(peer_id, auth_reply)
            
            # 消息处理逻辑将由UI组件处理
            if self.window:
                await self.window.handle_message(peer_id, message)
                
        except Exception as e:
            logging.error(f"处理消息时出错: {e}")
            
    def on_login_successful(self, user_id: int, username: str):
        """登录成功的处理函数"""
        try:
            logging.info(f"用户登录成功: user_id={user_id}, username={username}")
            
            # 创建并显示主窗口
            self.window = MainWindow()
            
            # 设置连接
            self.loop.create_task(self.setup_connection(user_id, username))
            
            # 等待连接设置完成
            def check_connection():
                if self.connection_manager:
                    # 设置network_manager
                    self.window.set_network_manager(self.connection_manager)
                    # 显示主窗口
                    self.window.show()
                    # 隐藏登录窗口
                    self.login_widget.hide()
                else:
                    # 100ms后再次检查
                    QTimer.singleShot(100, check_connection)
            
            # 开始检查连接
            check_connection()
            
        except Exception as e:
            logging.error(f"处理登录成功时出错: {e}")
            
    def run(self):
        """运行应用程序"""
        try:
            self.app = QApplication(sys.argv)
            
            # 创建事件循环
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # 创建登录窗口
            self.login_widget = LoginWidget()
            self.login_widget.login_successful.connect(self.on_login_successful)
            self.login_widget.show()
            
            # 创建定时器以处理异步事件
            timer = QTimer()
            timer.timeout.connect(lambda: self._process_events())
            timer.start(10)  # 每10毫秒处理一次事件
            
            # 运行应用程序
            sys.exit(self.app.exec())
            
        except Exception as e:
            logging.error(f"运行应用程序时出错: {e}")
            sys.exit(1)
            
    def _process_events(self):
        """处理异步事件"""
        self.loop.stop()
        self.loop.run_forever()
            
    async def cleanup(self):
        """清理资源"""
        if self.connection_manager:
            await self.connection_manager.stop()

def main():
    app = P2PChatApp()
    app.run()

if __name__ == "__main__":
    main() 