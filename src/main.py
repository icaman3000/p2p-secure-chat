import sys
import asyncio
import qasync
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from src.ui.main_window import MainWindow
from src.utils.database import init_database

def main():
    app = QApplication(sys.argv)
    
    # 创建事件循环
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # 初始化数据库（使用临时用户ID 0 来初始化系统数据库）
    init_database(0)
    
    # 创建主窗口
    window = MainWindow()
    window.show()
    
    # 创建定时器以处理异步事件
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(100)
    
    # 运行事件循环
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main() 