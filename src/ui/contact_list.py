from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QInputDialog,
    QMessageBox,
    QMenu
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont, QColor
from src.utils.database import (
    get_contacts,
    send_friend_request,
    handle_friend_request,
    get_pending_friend_requests,
    get_unread_message_counts,
    get_user_by_id
)
from src.utils.network import network_manager
import asyncio

class ContactList(QWidget):
    contact_selected = pyqtSignal(int)  # 发送联系人ID
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.setup_signals()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 添加联系人按钮
        add_button = QPushButton("Add Contact")
        add_button.clicked.connect(self.add_contact)
        layout.addWidget(add_button)
        
        # 联系人列表
        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.list_widget)
    
    def setup_signals(self):
        self.list_widget.itemClicked.connect(self.on_contact_selected)
        network_manager.friend_request_received.connect(self.handle_friend_request)
        network_manager.friend_response_received.connect(self.handle_friend_response)
        network_manager.connection_status_changed.connect(self.on_connection_status_changed)  # 监听连接状态变化
    
    def show_context_menu(self, position):
        menu = QMenu()
        add_contact_action = menu.addAction("Add Contact")
        add_contact_action.triggered.connect(self.add_contact)
        menu.exec(self.list_widget.mapToGlobal(position))
    
    def add_contact(self):
        username, ok = QInputDialog.getText(self, "Add Contact", "Enter username:")
        if ok and username:
            try:
                print(f"Attempting to send friend request to {username}")  # Debug log
                
                # 检查是否是自己的用户名
                if username == network_manager.username:
                    QMessageBox.warning(self, "Error", "You cannot add yourself as a contact")
                    return
                
                # 发送好友请求
                request = send_friend_request(network_manager.user_id, username)
                print(f"Friend request created: {request}")  # Debug log
                
                # 发送请求到服务器
                async def send_request():
                    try:
                        success = await network_manager.send_friend_request(
                            request["recipient_id"],
                            request["id"]
                        )
                        print(f"Friend request sent to server: {success}")  # Debug log
                        if not success:
                            QMessageBox.warning(self, "Error", "Failed to send friend request to server")
                    except Exception as e:
                        print(f"Error sending friend request: {e}")  # Debug log
                        QMessageBox.warning(self, "Error", f"Failed to send friend request: {e}")
                
                # 执行发送请求任务
                asyncio.create_task(send_request())
                QMessageBox.information(self, "Success", f"Friend request sent to {username}")
                
            except ValueError as e:
                print(f"Error in add_contact: {e}")  # Debug log
                if "Already in your contact list" in str(e):
                    QMessageBox.information(self, "Information", f"{username} is already in your contact list")
                elif "User not found" in str(e):
                    QMessageBox.warning(self, "Error", f"User '{username}' not found")
                elif "Friend request already sent" in str(e):
                    QMessageBox.information(self, "Information", f"You have already sent a friend request to {username}. Please wait for their response.")
                else:
                    QMessageBox.warning(self, "Error", str(e))
            except Exception as e:
                print(f"Error in add_contact: {e}")  # Debug log
                QMessageBox.warning(self, "Error", f"An error occurred: {str(e)}")
    
    def handle_friend_request(self, request):
        """处理收到的好友请求"""
        print(f"Received friend request: {request}")  # Debug log
        # 先刷新列表以显示新的请求
        self.load_contacts()
        
        reply = QMessageBox.question(
            self,
            "Friend Request",
            f"User {request['sender_username']} wants to add you as a contact. Accept?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        accepted = reply == QMessageBox.StandardButton.Yes
        try:
            print(f"Processing friend request response: accepted={accepted}")  # Debug log
            # 处理好友请求
            handle_friend_request(request["id"], network_manager.user_id, accepted)
            
            # 发送响应到服务器
            async def send_response():
                try:
                    success = await network_manager.send_friend_response(
                        request["id"],
                        request["sender_id"],
                        accepted
                    )
                    print(f"Friend response sent to server: {success}")  # Debug log
                    if not success:
                        QMessageBox.warning(self, "Error", "Failed to send response to server")
                except Exception as e:
                    print(f"Error sending friend response: {e}")  # Debug log
                    QMessageBox.warning(self, "Error", f"Failed to send response: {e}")
            
            asyncio.create_task(send_response())
            
            if accepted:
                self.load_contacts()  # 刷新联系人列表
            
        except Exception as e:
            print(f"Error handling friend request: {e}")  # Debug log
            QMessageBox.warning(self, "Error", f"Failed to process friend request: {str(e)}")
    
    def handle_friend_response(self, response):
        """处理好友请求的响应"""
        if response["accepted"]:
            QMessageBox.information(
                self,
                "Friend Request Accepted",
                f"{response['recipient_username']} accepted your friend request"
            )
            self.load_contacts()  # 刷新联系人列表
        else:
            QMessageBox.information(
                self,
                "Friend Request Rejected",
                f"{response['recipient_username']} rejected your friend request"
            )
    
    def load_contacts(self):
        """加载联系人列表"""
        try:
            self.list_widget.clear()
            contacts = get_contacts(network_manager.user_id)
            
            # 获取未读消息数量
            unread_counts = get_unread_message_counts(network_manager.user_id)
            
            # 检查是否有待处理的好友请求
            pending_requests = get_pending_friend_requests(network_manager.user_id)
            for request in pending_requests:
                item = QListWidgetItem(f"[Pending Request] {request['sender_username']}")
                item.setData(100, request)  # 存储请求数据
                self.list_widget.addItem(item)
            
            # 添加联系人
            for contact in contacts:
                contact_id = contact["id"]
                unread_count = unread_counts.get(contact_id, 0)
                
                # 创建联系人项
                display_name = contact["name"]
                if unread_count > 0:
                    display_name = f"{display_name} ({unread_count})"
                
                item = QListWidgetItem(display_name)
                item.setData(100, contact)  # 存储联系人数据
                
                # 如果有未读消息，设置字体为粗体和蓝色
                if unread_count > 0:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor(0, 0, 255))
                
                self.list_widget.addItem(item)
        except Exception as e:
            print(f"Error loading contacts: {e}")
    
    def update_unread_count(self, contact_id):
        """更新特定联系人的未读消息数量"""
        # 获取未读消息数量
        unread_counts = get_unread_message_counts(network_manager.user_id)
        unread_count = unread_counts.get(contact_id, 0)
        
        # 查找并更新联系人项
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            contact_data = item.data(100)
            if isinstance(contact_data, dict) and contact_data.get("id") == contact_id:
                # 获取联系人信息
                contact = get_contacts(network_manager.user_id)[i]
                display_name = contact["name"]
                
                if unread_count > 0:
                    display_name = f"{display_name} ({unread_count})"
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor(0, 0, 255))
                else:
                    font = item.font()
                    font.setBold(False)
                    item.setFont(font)
                    item.setForeground(QColor(0, 0, 0))
                
                item.setText(display_name)
                break
    
    def on_contact_selected(self, item):
        """处理联系人选择事件"""
        contact_data = item.data(100)
        if isinstance(contact_data, dict) and "id" in contact_data:
            self.contact_selected.emit(contact_data["id"]) 
    
    def on_connection_status_changed(self, connected):
        """处理连接状态变化"""
        if connected:
            self.load_contacts()  # 在连接建立后加载联系人列表 