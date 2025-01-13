from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QInputDialog,
    QMessageBox,
    QMenu,
    QHBoxLayout,
    QDialog,
    QLabel,
    QAbstractItemView
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont, QColor
from src.utils.database import (
    get_contacts,
    send_friend_request,
    handle_friend_request,
    get_pending_friend_requests,
    get_unread_message_counts,
    get_user_by_id,
    get_sent_friend_requests
)
from src.utils.network import network_manager
import asyncio

class ContactList(QListWidget):
    contact_selected = pyqtSignal(int)  # 发送选中的联系人ID
    contact_added = pyqtSignal(int)  # 发送新添加的联系人ID
    
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.itemClicked.connect(self.on_item_clicked)
        self.load_contacts()
        self.init_ui()
        self.setup_signals()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 添加按钮布局
        button_layout = QHBoxLayout()
        
        # 添加联系人按钮
        add_button = QPushButton("添加联系人")
        add_button.clicked.connect(self.add_contact)
        button_layout.addWidget(add_button)
        
        # 查看待处理请求按钮
        pending_button = QPushButton("待处理请求")
        pending_button.clicked.connect(self.show_pending_requests)
        button_layout.addWidget(pending_button)
        
        layout.addLayout(button_layout)
        
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
    
    def show_pending_requests(self):
        """显示待处理的好友请求"""
        try:
            pending_requests = get_pending_friend_requests(network_manager.user_id)
            sent_requests = get_sent_friend_requests(network_manager.user_id)
            
            if not pending_requests and not sent_requests:
                QMessageBox.information(self, "待处理请求", "没有待处理的好友请求")
                return
            
            # 创建一个对话框来显示请求
            dialog = QDialog(self)
            dialog.setWindowTitle("待处理请求")
            layout = QVBoxLayout()
            
            # 显示收到的请求
            if pending_requests:
                layout.addWidget(QLabel("收到的请求："))
                for req in pending_requests:
                    req_layout = QHBoxLayout()
                    req_layout.addWidget(QLabel(f"来自：{req['sender_username']} ({req['created_at']})"))
                    
                    # 添加接受按钮
                    accept_btn = QPushButton("接受")
                    accept_btn.clicked.connect(lambda checked, r=req: self._handle_request_from_dialog(r, True))
                    req_layout.addWidget(accept_btn)
                    
                    # 添加拒绝按钮
                    reject_btn = QPushButton("拒绝")
                    reject_btn.clicked.connect(lambda checked, r=req: self._handle_request_from_dialog(r, False))
                    req_layout.addWidget(reject_btn)
                    
                    # 将这个请求的布局添加到主布局
                    container = QWidget()
                    container.setLayout(req_layout)
                    layout.addWidget(container)
                
                layout.addWidget(QLabel(""))  # 添加空行作为分隔
            
            # 显示发出的请求
            if sent_requests:
                layout.addWidget(QLabel("发出的请求："))
                for req in sent_requests:
                    layout.addWidget(QLabel(f"发给：{req['recipient_username']} ({req['created_at']})"))
            
            # 添加关闭按钮
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dialog.close)
            layout.addWidget(close_btn)
            
            dialog.setLayout(layout)
            dialog.exec()
            
        except Exception as e:
            print(f"Error showing pending requests: {e}")
            QMessageBox.warning(self, "错误", f"无法获取待处理请求：{str(e)}")
    
    def _handle_request_from_dialog(self, request, accept):
        """处理对话框中的好友请求"""
        try:
            print(f"Processing friend request response: accepted={accept}")  # Debug log
            # 处理好友请求
            handle_friend_request(request["id"], network_manager.user_id, accept)
            
            # 发送响应到服务器
            async def send_response():
                try:
                    success = await network_manager.send_friend_response(
                        request["id"],
                        request["sender_id"],
                        accept
                    )
                    print(f"Friend response sent to server: {success}")  # Debug log
                    if not success:
                        QMessageBox.warning(self, "错误", "无法发送响应到服务器")
                    else:
                        QMessageBox.information(self, "成功", 
                            f"已{'接受' if accept else '拒绝'} {request['sender_username']} 的好友请求")
                        if accept:
                            self.load_contacts()  # 刷新联系人列表
                except Exception as e:
                    print(f"Error sending friend response: {e}")  # Debug log
                    QMessageBox.warning(self, "错误", f"发送响应失败：{e}")
            
            # 执行发送响应任务
            asyncio.create_task(send_response())
            
        except Exception as e:
            print(f"Error handling friend request: {e}")  # Debug log
            QMessageBox.warning(self, "错误", f"处理好友请求失败：{str(e)}")
    
    def handle_friend_request(self, request):
        """处理收到的好友请求"""
        print(f"Received friend request: {request}")  # Debug log
        # 先刷新列表以显示新的请求
        self.load_contacts()
        
        reply = QMessageBox.question(
            self,
            "好友请求",
            f"用户 {request['sender_username']} 想添加您为好友，是否接受？",
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
                        QMessageBox.warning(self, "错误", "无法发送响应到服务器")
                except Exception as e:
                    print(f"Error sending friend response: {e}")  # Debug log
                    QMessageBox.warning(self, "错误", f"发送响应失败：{e}")
            
            asyncio.create_task(send_response())
            
            if accepted:
                self.load_contacts()  # 刷新联系人列表
                QMessageBox.information(self, "成功", f"已接受 {request['sender_username']} 的好友请求")
            else:
                QMessageBox.information(self, "提示", f"已拒绝 {request['sender_username']} 的好友请求")
            
        except Exception as e:
            print(f"Error handling friend request: {e}")  # Debug log
            QMessageBox.warning(self, "错误", f"处理好友请求失败：{str(e)}")
    
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
            contacts = get_contacts(self.user_id)
            for contact in contacts:
                self.add_contact(contact["id"], contact["name"])
        except Exception as e:
            print(f"Error loading contacts: {e}")
    
    def update_unread_count(self, contact_id, count):
        """更新未读消息数量"""
        for i in range(self.count()):
            item = self.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == contact_id:
                contact_name = item.data(Qt.ItemDataRole.DisplayRole)
                if '(' in contact_name:
                    contact_name = contact_name.split('(')[0].strip()
                if count > 0:
                    item.setText(f"{contact_name} ({count})")
                else:
                    item.setText(contact_name)
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
    
    def add_contact(self):
        username, ok = QInputDialog.getText(self, "添加联系人", "请输入用户名：")
        if ok and username:
            try:
                print(f"Attempting to send friend request to {username}")  # Debug log
                
                # 检查是否是自己的用户名
                if username == network_manager.username:
                    QMessageBox.warning(self, "错误", "不能添加自己为联系人")
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
                            QMessageBox.warning(self, "错误", "无法发送好友请求到服务器")
                    except Exception as e:
                        print(f"Error sending friend request: {e}")  # Debug log
                        QMessageBox.warning(self, "错误", f"发送好友请求失败：{e}")
                
                # 执行发送请求任务
                asyncio.create_task(send_request())
                QMessageBox.information(self, "成功", f"已发送好友请求给 {username}")
                
            except ValueError as e:
                print(f"Error in add_contact: {e}")  # Debug log
                error_msg = str(e)
                if "Already in your contact list" in error_msg:
                    QMessageBox.information(self, "提示", f"{username} 已经在您的联系人列表中")
                elif "User not found" in error_msg:
                    QMessageBox.warning(self, "错误", f"找不到用户 '{username}'")
                elif "Friend request already sent and pending" in error_msg:
                    reply = QMessageBox.question(
                        self,
                        "待处理请求",
                        f"您已经向 {username} 发送了好友请求，是否查看待处理请求？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.show_pending_requests()
                elif "Friend request was already accepted" in error_msg:
                    QMessageBox.information(self, "提示", 
                        f"您与 {username} 的好友请求已被接受，请刷新联系人列表。")
                    self.load_contacts()
                else:
                    QMessageBox.warning(self, "错误", error_msg)
            except Exception as e:
                print(f"Error in add_contact: {e}")  # Debug log
                QMessageBox.warning(self, "错误", f"发生错误：{str(e)}") 
    
    def on_item_clicked(self, item):
        """处理联系人选择"""
        contact_id = item.data(Qt.ItemDataRole.UserRole)
        if contact_id:
            self.contact_selected.emit(contact_id)
            self.update_unread_count(contact_id, 0)  # Reset unread count when selected 
    
    def add_contact(self, contact_id, contact_name):
        """添加新联系人"""
        item = QListWidgetItem(contact_name)
        item.setData(Qt.ItemDataRole.UserRole, contact_id)
        self.addItem(item)
        self.contact_added.emit(contact_id) 