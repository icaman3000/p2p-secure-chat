import sys
import asyncio
import logging
import os
from typing import Optional, Tuple
from dotenv import load_dotenv
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from src.ui.main_window import MainWindow
from src.utils.database import init_database
from src.utils.connection_manager import ConnectionManager
from src.utils.network import NetworkManager
from src.utils.relay_server import RelayServer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.getenv('LOG_FILE', 'app.log'))
    ]
)

class P2PChatApp:
    """P2P聊天应用主类"""
    
    def __init__(self):
        self.app = None
        self.window = None
        self.network_manager = None
        self.connection_manager = None
        self.relay_server = None
        self.stun_results = []
        
    async def start_relay_server(self) -> Optional[RelayServer]:
        """启动中继服务器"""
        try:
            relay_port = int(os.getenv('RELAY_PORT', '8765'))
            relay_server = RelayServer(port=relay_port)
            await relay_server.start()
            logging.info(f"中继服务器已启动在端口 {relay_port}")
            return relay_server
        except Exception as e:
            logging.error(f"中继服务器启动失败: {e}")
            return None

    async def init_network(self) -> Tuple[NetworkManager, ConnectionManager]:
        """初始化网络连接"""
        # 创建网络管理器
        network_manager = NetworkManager()
        
        # 配置STUN/TURN服务器
        stun_servers = [
            (os.getenv('STUN_SERVER1', 'stun.l.google.com'), int(os.getenv('STUN_PORT1', '19302'))),
            (os.getenv('STUN_SERVER2', 'stun1.l.google.com'), int(os.getenv('STUN_PORT2', '19302')))
        ]
        
        turn_servers = []
        if os.getenv('TURN_SERVER'):
            turn_servers.append({
                'server': os.getenv('TURN_SERVER'),
                'port': int(os.getenv('TURN_PORT', '3478')),
                'username': os.getenv('TURN_USERNAME', ''),
                'password': os.getenv('TURN_PASSWORD', '')
            })
        
        # 配置中继服务器
        relay_host = os.getenv('RELAY_HOST', 'localhost')
        relay_port = int(os.getenv('RELAY_PORT', '8765'))
        relay_server = f"ws://{relay_host}:{relay_port}"
        
        # 初始化连接管理器
        connection_manager = ConnectionManager()
        
        # 设置重连参数
        connection_manager.max_reconnect_attempts = int(os.getenv('MAX_RECONNECT_ATTEMPTS', '3'))
        connection_manager.reconnect_delay = float(os.getenv('RECONNECT_DELAY', '2.0'))
        
        # 启动网络服务
        try:
            await network_manager.start()
            await connection_manager.start(port=int(os.getenv('LOCAL_PORT', '0')))
            
            # 保存STUN绑定结果
            self.stun_results = connection_manager.stun_results
            
            return network_manager, connection_manager
        except Exception as e:
            logging.error(f"网络初始化失败: {e}")
            raise

    async def handle_message(self, peer_id: str, message: dict):
        """处理接收到的消息"""
        try:
            if self.window:
                await self.window.handle_message(peer_id, message)
        except Exception as e:
            logging.error(f"处理消息失败: {e}")

    async def start(self):
        """启动应用"""
        try:
            # 加载环境变量
            load_dotenv()
            
            # 创建Qt应用
            self.app = QApplication(sys.argv)
            
            # 初始化数据库
            init_database(0)
            
            # 启动中继服务器
            self.relay_server = await self.start_relay_server()
            
            # 初始化网络
            self.network_manager, self.connection_manager = await self.init_network()
            
            # 设置消息处理器
            self.connection_manager.set_message_handler(self.handle_message)
            
            # 创建主窗口
            self.window = MainWindow(
                network_manager=self.network_manager,
                connection_manager=self.connection_manager
            )
            self.window.show()
            
            # 创建定时器以处理异步事件
            timer = QTimer()
            timer.timeout.connect(lambda: None)
            timer.start(100)
            
            # 运行事件循环
            return await self.run_event_loop()
            
        except Exception as e:
            logging.error(f"启动失败: {e}")
            await self.cleanup()
            raise

    async def run_event_loop(self):
        """运行事件循环"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_forever()
        except Exception as e:
            logging.error(f"事件循环异常: {e}")
            raise
        finally:
            await self.cleanup()

    async def cleanup(self):
        """清理资源"""
        if self.connection_manager:
            await self.connection_manager.stop()
        if self.network_manager:
            await self.network_manager.stop()
        if self.relay_server:
            await self.relay_server.stop()
            logging.info("中继服务器已停止")

def main():
    """程序入口"""
    app = P2PChatApp()
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        logging.info("程序已终止")
    except Exception as e:
        logging.error(f"程序异常退出: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 