import sys
import asyncio
import qasync
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from src.ui.main_window import MainWindow
from src.utils.network import network_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)

logger = logging.getLogger(__name__)

async def cleanup():
    """清理资源"""
    try:
        await network_manager.stop()
        logger.info("Application cleanup completed")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

def main():
    try:
        logger.info("Starting application...")
        app = QApplication(sys.argv)
        
        # 创建事件循环
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        
        # 创建主窗口
        window = MainWindow()
        window.show()
        
        # 创建定时器以处理异步事件
        timer = QTimer()
        timer.timeout.connect(lambda: None)
        timer.start(100)
        
        # 注册清理函数
        app.aboutToQuit.connect(lambda: asyncio.create_task(cleanup()))
        
        # 运行事件循环
        with loop:
            logger.info("Application main loop started")
            loop.run_forever()
            
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 