from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QStackedWidget,
    QLabel,
    QProgressBar,
    QMessageBox,
    QStyleFactory,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPalette, QColor
from src.ui.chat_widget import ChatWidget
from src.ui.contact_list import ContactList
from src.ui.login_widget import LoginWidget
from src.utils.network import network_manager
import asyncio
import qasync
import logging
import os

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, user_id, username):
        super().__init__()
        self.user_id = user_id
        self.username = username
        self.network_manager = None
        self.contact_list = None
        self.chat_widgets = {}
        self.unread_counts = {}
        
        # 从环境变量获取端口配置
        self.node_port = int(os.getenv('NODE_PORT', 8084))
        self.discovery_port = int(os.getenv('DISCOVERY_PORT', 8085))
        
        self.init_ui()
        self.init_network()
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle(f"P2P Chat - {self.username}")
        self.setGeometry(100, 100, 800, 600)
        
        # 创建主窗口布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        
        # 创建联系人列表
        self.contact_list = ContactList(self.user_id)
        layout.addWidget(self.contact_list, 1)
        
        # 创建聊天区域容器
        self.chat_container = QStackedWidget()
        layout.addWidget(self.chat_container, 2)
        
        # 连接信号
        self.contact_list.contact_selected.connect(self.show_chat)
        self.contact_list.contact_added.connect(self.handle_contact_added)
        
    def init_network(self):
        """初始化网络管理器"""
        try:
            self.network_manager = NetworkManager(
                node_port=self.node_port,
                discovery_port=self.discovery_port
            )
            
            # 连接网络信号
            self.network_manager.message_received.connect(self.handle_message)
            self.network_manager.friend_request_received.connect(self.handle_friend_request)
            self.network_manager.friend_response_received.connect(self.handle_friend_response)
            self.network_manager.connection_status_changed.connect(self.handle_connection_status)
            
            # 启动网络管理器
            asyncio.create_task(self.network_manager.start(self.user_id, self.username))
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to initialize network: {e}")
            
    def show_chat(self, contact_id, contact_name):
        """显示与指定联系人的聊天窗口"""
        if contact_id not in self.chat_widgets:
            # 创建新的聊天窗口
            chat_widget = ChatWidget(
                self.user_id,
                contact_id,
                contact_name,
                self.network_manager
            )
            self.chat_widgets[contact_id] = chat_widget
            self.chat_container.addWidget(chat_widget)
            
        # 显示聊天窗口
        chat_widget = self.chat_widgets[contact_id]
        self.chat_container.setCurrentWidget(chat_widget)
        
        # 清除未读消息计数
        if contact_id in self.unread_counts:
            self.unread_counts[contact_id] = 0
            self.contact_list.update_unread_count(contact_id, 0)
            
    def handle_message(self, message):
        """处理接收到的消息"""
        try:
            sender_id = message["sender_id"]
            
            # 如果发送者的聊天窗口不存在，创建一个
            if sender_id not in self.chat_widgets:
                sender_name = message.get("sender_username", f"User {sender_id}")
                chat_widget = ChatWidget(
                    self.user_id,
                    sender_id,
                    sender_name,
                    self.network_manager
                )
                self.chat_widgets[sender_id] = chat_widget
                self.chat_container.addWidget(chat_widget)
            
            # 更新聊天窗口
            chat_widget = self.chat_widgets[sender_id]
            chat_widget.add_message(message)
            
            # 如果当前没有显示该聊天窗口，增加未读消息计数
            if self.chat_container.currentWidget() != chat_widget:
                self.unread_counts[sender_id] = self.unread_counts.get(sender_id, 0) + 1
                self.contact_list.update_unread_count(sender_id, self.unread_counts[sender_id])
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error handling message: {e}")
            
    def handle_friend_request(self, request):
        """处理好友请求"""
        try:
            sender_id = request["sender_id"]
            sender_name = request.get("sender_username", f"User {sender_id}")
            
            # 显示确认对话框
            reply = QMessageBox.question(
                self,
                "Friend Request",
                f"Accept friend request from {sender_name}?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            # 发送响应
            accepted = reply == QMessageBox.Yes
            asyncio.create_task(
                self.network_manager.handle_friend_response(sender_id, accepted)
            )
            
            # 如果接受请求，添加到联系人列表
            if accepted:
                self.contact_list.add_contact(sender_id, sender_name)
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error handling friend request: {e}")
            
    def handle_friend_response(self, response):
        """处理好友请求响应"""
        try:
            sender_id = response["sender_id"]
            sender_name = response.get("sender_username", f"User {sender_id}")
            accepted = response["accepted"]
            
            if accepted:
                # 添加到联系人列表
                self.contact_list.add_contact(sender_id, sender_name)
                QMessageBox.information(
                    self,
                    "Friend Request Accepted",
                    f"{sender_name} accepted your friend request"
                )
            else:
                QMessageBox.information(
                    self,
                    "Friend Request Rejected",
                    f"{sender_name} rejected your friend request"
                )
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error handling friend response: {e}")
            
    def handle_contact_added(self, contact_id, contact_name):
        """处理新添加的联系人"""
        try:
            # 发送好友请求
            asyncio.create_task(
                self.network_manager.send_friend_request(contact_id)
            )
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error sending friend request: {e}")
            
    def handle_connection_status(self, connected):
        """处理连接状态变化"""
        status = "Connected" if connected else "Disconnected"
        self.statusBar().showMessage(status)
        
    def closeEvent(self, event):
        """窗口关闭事件"""
        try:
            # 停止网络管理器
            if self.network_manager:
                asyncio.create_task(self.network_manager.stop())
            event.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error closing application: {e}")
            event.ignore() 