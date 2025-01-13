from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QStackedWidget,
    QLabel,
)
from PyQt6.QtCore import Qt
from src.ui.chat_widget import ChatWidget
from src.ui.contact_list import ContactList
from src.ui.login_widget import LoginWidget
from src.utils.network import network_manager
import asyncio
import qasync

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Secure Chat")
        self.setMinimumSize(800, 600)
        
        # 创建主窗口部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 创建主布局
        self.main_layout = QHBoxLayout(self.central_widget)
        
        # 创建左侧布局
        left_layout = QVBoxLayout()
        
        # 添加用户信息标签
        self.user_info_label = QLabel("Not logged in")
        self.user_info_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        left_layout.addWidget(self.user_info_label)
        
        # 添加状态标签
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: red;")
        left_layout.addWidget(self.status_label)
        
        # 创建左侧联系人列表
        self.contact_list = ContactList()
        left_layout.addWidget(self.contact_list)
        
        self.main_layout.addLayout(left_layout, 1)
        
        # 创建右侧聊天区域
        self.chat_stack = QStackedWidget()
        self.main_layout.addWidget(self.chat_stack, 3)
        
        # 创建登录窗口
        self.login_widget = LoginWidget()
        self.chat_stack.addWidget(self.login_widget)
        
        # 连接信号
        self.contact_list.contact_selected.connect(self.show_chat)
        self.login_widget.login_successful.connect(self.on_login_successful)
        network_manager.connection_status_changed.connect(self.on_connection_status_changed)
        network_manager.message_received.connect(self.on_message_received)
    
    def show_chat(self, contact_id):
        # 显示与选中联系人的聊天界面
        chat_key = f"chat_{contact_id}"
        if not hasattr(self, chat_key):
            chat_widget = ChatWidget(contact_id)
            setattr(self, chat_key, chat_widget)
            self.chat_stack.addWidget(chat_widget)
        
        chat_widget = getattr(self, chat_key)
        self.chat_stack.setCurrentWidget(chat_widget)
        
        # 标记消息为已读并更新联系人列表
        from src.utils.database import mark_messages_as_read
        mark_messages_as_read(network_manager.user_id, contact_id)
        self.contact_list.update_unread_count(contact_id)
    
    def on_login_successful(self, user_id, username):
        """登录成功的处理函数"""
        self.user_id = user_id
        self.username = username
        
        # 显示主界面
        self.show_main_interface()
        
        # 连接到服务器
        asyncio.create_task(network_manager.start(user_id, username))
        
        # 更新未读消息数
        self.update_unread_counts()
    
    def on_connection_status_changed(self, connected):
        # 更新连接状态显示
        if connected:
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("color: green;")
            # 连接成功后加载联系人列表
            self.contact_list.load_contacts()
        else:
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("color: red;")
    
    def on_message_received(self, message):
        # 处理接收到的消息
        sender_id = message["sender_id"]
        
        # 如果没有对应的聊天窗口，创建一个
        if not hasattr(self, f"chat_{sender_id}"):
            chat_widget = ChatWidget(sender_id)
            setattr(self, f"chat_{sender_id}", chat_widget)
            self.chat_stack.addWidget(chat_widget)
        
        # 获取聊天窗口并显示消息
        chat_widget = getattr(self, f"chat_{sender_id}")
        chat_widget.receive_message(message)
        
        # 如果当前不是这个聊天窗口，更新未读消息数量
        if self.chat_stack.currentWidget() != chat_widget:
            self.contact_list.update_unread_count(sender_id)
    
    def closeEvent(self, event):
        # 关闭窗口时断开连接
        asyncio.create_task(network_manager.disconnect())
        super().closeEvent(event) 
    
    def show_main_interface(self):
        """显示主界面"""
        # 更新用户信息显示
        self.user_info_label.setText(f"Logged in as: {self.username}")
        
        # 加载联系人列表
        self.contact_list.load_contacts()
        
        # 创建默认聊天页面
        default_chat = ChatWidget(None)
        self.chat_stack.addWidget(default_chat)
        self.chat_stack.setCurrentWidget(default_chat) 
    
    def update_unread_counts(self):
        """更新所有联系人的未读消息数"""
        if hasattr(self, 'contact_list'):
            self.contact_list.load_contacts()  # 这会刷新联系人列表，包括未读消息数 