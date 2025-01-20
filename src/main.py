import sys
import asyncio
import logging
import os
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
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def start_relay_server():
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

async def init_network():
    """初始化网络连接"""
    # 加载环境变量
    load_dotenv()
    
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
    connection_manager = ConnectionManager(
        stun_servers=stun_servers,
        turn_servers=turn_servers,
        relay_server=relay_server
    )
    
    # 启动网络服务
    await network_manager.start()
    await connection_manager.start()
    
    return network_manager, connection_manager

async def main():
    # 创建应用
    app = QApplication(sys.argv)
    
    # 创建事件循环
    loop = asyncio.get_event_loop()
    
    try:
        # 初始化数据库
        init_database(0)
        
        # 启动中继服务器
        relay_server = await start_relay_server()
        
        # 初始化网络
        network_manager, connection_manager = await init_network()
        
        # 创建主窗口
        window = MainWindow(network_manager=network_manager, connection_manager=connection_manager)
        window.show()
        
        # 创建定时器以处理异步事件
        timer = QTimer()
        timer.timeout.connect(lambda: None)
        timer.start(100)
        
        # 运行事件循环
        await loop.run_forever()
        
    except Exception as e:
        logging.error(f"启动失败: {e}")
        raise
    finally:
        # 清理资源
        if 'network_manager' in locals():
            await network_manager.stop()
        if 'connection_manager' in locals():
            await connection_manager.stop()
        if 'relay_server' in locals() and relay_server:
            await relay_server.stop()
            logging.info("中继服务器已停止")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("程序已终止")
    except Exception as e:
        logging.error(f"程序异常退出: {e}")
        sys.exit(1) 