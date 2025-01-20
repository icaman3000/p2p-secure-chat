import sys
import logging
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
    QStatusBar,
    QPushButton,
    QTextEdit,
    QLineEdit,
    QSplitter
)
from PyQt6.QtCore import Qt, QTimer, QMetaObject, Q_ARG
from PyQt6.QtGui import QPalette, QColor
from src.ui.chat_widget import ChatWidget
from src.ui.contact_list import ContactList
from src.ui.login_widget import LoginWidget
from src.utils.network import NetworkManager
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.network_manager = None
        self.chat_widgets = {}
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle('P2P Chat')
        self.setGeometry(100, 100, 800, 600)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        layout = QHBoxLayout(central_widget)
        
        # 创建左侧面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # 网络信息显示
        self.network_info_label = QLabel("Network Info")
        self.network_info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.network_info_label.setWordWrap(True)
        left_layout.addWidget(self.network_info_label)
        
        # 添加好友区域
        add_friend_layout = QHBoxLayout()
        self.peer_id_input = QLineEdit()
        self.peer_id_input.setPlaceholderText("Enter Peer ID")
        add_friend_layout.addWidget(self.peer_id_input)
        
        add_friend_button = QPushButton("Add Friend")
        add_friend_button.clicked.connect(self.add_friend)
        add_friend_layout.addWidget(add_friend_button)
        
        left_layout.addLayout(add_friend_layout)
        
        # 好友列表
        self.friend_list = QTextEdit()
        self.friend_list.setReadOnly(True)
        left_layout.addWidget(self.friend_list)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        
        # 创建右侧聊天区域
        self.chat_area = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_area)
        splitter.addWidget(self.chat_area)
        
        # 设置分割器的初始大小
        splitter.setSizes([200, 600])
        
        layout.addWidget(splitter)
        
    def set_network_manager(self, manager):
        """设置网络管理器"""
        self.network_manager = manager
        if manager:
            manager.network_info_updated.connect(self._update_network_info)
            
    def _update_network_info(self, info: dict):
        """更新网络信息显示"""
        if not info:
            return
            
        network_info = []
        if info.get('local_ip'):
            network_info.append(f"Local IP: {info['local_ip']}")
        if info.get('public_ip'):
            network_info.append(f"Public IP: {info['public_ip']}")
        if info.get('stun_results'):
            network_info.append("\nSTUN Results:")
            for result in info['stun_results']:
                network_info.append(f"- Server: {result.get('server', 'Unknown')}")
                network_info.append(f"  NAT Type: {result.get('nat_type', 'Unknown')}")
                network_info.append(f"  External IP: {result.get('external_ip', 'Unknown')}")
                network_info.append(f"  External Port: {result.get('external_port', 'Unknown')}")
            
        self.network_info_label.setText("\n".join(network_info))
        
    async def _send_friend_request(self, peer_id: str):
        """发送好友请求（异步方法）"""
        try:
            # 构建好友请求消息
            request_message = {
                "type": "friend_request",
                "sender_id": self.network_manager.user_id,
                "sender_username": self.network_manager.username,
                "timestamp": datetime.now().timestamp()
            }
            
            # 尝试发送消息
            success = await self.network_manager.send_message(peer_id, request_message)
            
            if success:
                QMessageBox.information(self, "Friend Request", "Friend request sent!")
            else:
                QMessageBox.warning(self, "Error", "Failed to send friend request. Please try again later.")
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to send friend request: {str(e)}")
            
    def add_friend(self):
        """添加好友"""
        peer_id = self.peer_id_input.text().strip()
        if not peer_id:
            QMessageBox.warning(self, "Warning", "Please enter a peer ID")
            return
            
        # 获取事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        # 发送好友请求
        loop.create_task(self._send_friend_request(peer_id))
        self.peer_id_input.clear()
        
    def _process_message(self, peer_id: str, message: dict):
        """处理接收到的消息（同步方法）"""
        msg_type = message.get("type")
        
        if msg_type == "friend_request":
            # 处理好友请求
            sender_id = message.get("sender_id")
            sender_username = message.get("sender_username")
            
            reply = QMessageBox.question(
                self,
                "Friend Request",
                f"User {sender_username} (ID: {sender_id}) wants to add you as a friend. Accept?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            # 准备回复消息
            response_message = {
                "type": "friend_response",
                "accepted": reply == QMessageBox.StandardButton.Yes,
                "sender_id": self.network_manager.user_id,
                "sender_username": self.network_manager.username,
                "timestamp": datetime.now().timestamp()
            }
            
            # 发送回复
            asyncio.create_task(self.network_manager.send_message(sender_id, response_message))
            
            # 如果接受请求，添加好友关系
            if reply == QMessageBox.StandardButton.Yes:
                from src.utils.database import add_friend
                
                # 添加到自己的好友列表
                success, message = add_friend(
                    self.network_manager.user_id,
                    sender_id,
                    sender_username
                )
                if not success:
                    QMessageBox.warning(self, "Error", f"Failed to add friend: {message}")
                    return
                    
                # 创建聊天窗口
                if sender_id not in self.chat_widgets:
                    chat_widget = ChatWidget(sender_id, self.network_manager)
                    self.chat_widgets[sender_id] = chat_widget
                    self.chat_layout.addWidget(chat_widget)
                    
                # 更新好友列表显示
                self.update_friend_list()
                    
        elif msg_type == "friend_response":
            # 处理好友请求回复
            sender_id = message.get("sender_id")
            sender_username = message.get("sender_username")
            accepted = message.get("accepted", False)
            
            if accepted:
                # 添加到自己的好友列表
                from src.utils.database import add_friend
                success, message = add_friend(
                    self.network_manager.user_id,
                    sender_id,
                    sender_username
                )
                
                if success:
                    QMessageBox.information(
                        self,
                        "Friend Request Accepted",
                        f"User {sender_username} accepted your friend request!"
                    )
                    
                    # 创建聊天窗口
                    if sender_id not in self.chat_widgets:
                        chat_widget = ChatWidget(sender_id, self.network_manager)
                        self.chat_widgets[sender_id] = chat_widget
                        self.chat_layout.addWidget(chat_widget)
                        
                    # 更新好友列表显示
                    self.update_friend_list()
                else:
                    QMessageBox.warning(
                        self,
                        "Error",
                        f"Failed to add friend: {message}"
                    )
            else:
                QMessageBox.information(
                    self,
                    "Friend Request Rejected",
                    f"User {sender_username} rejected your friend request."
                )
                
        else:
            # 处理普通消息
            if peer_id not in self.chat_widgets:
                chat_widget = ChatWidget(peer_id, self.network_manager)
                self.chat_widgets[peer_id] = chat_widget
                self.chat_layout.addWidget(chat_widget)
                
            # 创建异步任务来处理消息
            asyncio.create_task(self.chat_widgets[peer_id].handle_message(message))
        
    async def handle_message(self, peer_id: str, message: dict):
        """处理接收到的消息（异步方法）"""
        # 在主线程中处理UI更新
        QMetaObject.invokeMethod(
            self,
            "_process_message",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, peer_id),
            Q_ARG(dict, message)
        )
        
    def init_theme(self):
        """初始化应用主题"""
        # 设置应用样式
        self.setStyle(QStyleFactory.create("Fusion"))
        
        # 创建深色主题调色板
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        
        self.setPalette(palette)
    
    def show_chat(self, contact_id):
        """显示与选中联系人的聊天界面"""
        try:
            # 显示加载指示器
            self.progress_bar.setRange(0, 0)
            self.progress_bar.show()
            
            # 延迟加载聊天窗口
            chat_widget = self.chat_widgets.get(contact_id)
            if not chat_widget:
                chat_widget = ChatWidget(contact_id)
                self.chat_widgets[contact_id] = chat_widget
                self.chat_stack.addWidget(chat_widget)
            
            self.chat_stack.setCurrentWidget(chat_widget)
            
            # 标记消息为已读并更新联系人列表
            from src.utils.database import mark_messages_as_read
            mark_messages_as_read(self.network_manager.user_id, contact_id)
            self.contact_list.update_unread_count(contact_id)
            
        except Exception as e:
            logger.error(f"Error showing chat: {e}")
            QMessageBox.warning(self, "Error", f"Failed to open chat: {str(e)}")
        
        finally:
            # 隐藏加载指示器
            self.progress_bar.hide()
    
    def check_pending_friend_requests(self):
        """检查待处理的好友请求"""
        try:
            from src.utils.database import get_pending_friend_requests
            requests = get_pending_friend_requests(self.network_manager.user_id)
            
            for request in requests:
                reply = QMessageBox.question(
                    self,
                    "Pending Friend Request",
                    f"User {request['sender_username']} (ID: {request['sender_id']}) wants to add you as a friend.\n"
                    f"Request sent at: {request['created_at']}\n"
                    "Accept?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                # 处理好友请求
                from src.utils.database import process_friend_request
                success, message = process_friend_request(
                    request['id'],
                    reply == QMessageBox.StandardButton.Yes
                )
                
                if not success:
                    QMessageBox.warning(self, "Error", f"Failed to process friend request: {message}")
                    continue
                    
                # 如果接受请求，创建聊天窗口
                if reply == QMessageBox.StandardButton.Yes:
                    if request['sender_id'] not in self.chat_widgets:
                        chat_widget = ChatWidget(request['sender_id'], self.network_manager)
                        self.chat_widgets[request['sender_id']] = chat_widget
                        self.chat_layout.addWidget(chat_widget)
                        
                    # 更新好友列表显示
                    self.update_friend_list()
                    
        except Exception as e:
            logger.error(f"Error checking pending friend requests: {e}")
            
    async def on_login_successful(self, user_id: int, username: str):
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
                    # 注册设备
                    from src.utils.database import register_device
                    success, message = register_device(
                        user_id,
                        self.connection_manager.device_id
                    )
                    
                    if not success:
                        QMessageBox.warning(self, "Error", f"Failed to register device: {message}")
                        return
                        
                    # 设置network_manager
                    self.window.set_network_manager(self.connection_manager)
                    
                    # 显示主窗口
                    self.window.show()
                    
                    # 隐藏登录窗口
                    self.login_widget.hide()
                    
                    # 检查待处理的好友请求
                    self.window.check_pending_friend_requests()
                    
                    # 启动设备发现
                    self.loop.create_task(self.connection_manager.broadcast_device_discovery())
                else:
                    # 100ms后再次检查
                    QTimer.singleShot(100, check_connection)
            
            # 开始检查连接
            check_connection()
            
        except Exception as e:
            logging.error(f"处理登录成功时出错: {e}")
    
    async def _connect_to_network(self):
        """连接到网络（异步）"""
        try:
            # 尝试从8000开始，每次失败时端口号加1
            port = 8000
            max_retries = 10
            
            for attempt in range(max_retries):
                try:
                    if await self.network_manager.start(port):
                        print(f"网络连接已建立: user_id={self.user_id}, port={port}")
                        
                        # 更新未读消息数
                        self.update_unread_counts()
                        
                        # 再次刷新联系人列表以确保最新状态
                        print("正在刷新联系人列表...")
                        contacts = self.contact_list.load_contacts()
                        print(f"联系人列表已更新: {contacts}")
                        break
                except Exception as e:
                    if "address already in use" in str(e):
                        print(f"端口 {port} 已被占用，尝试下一个端口")
                        port += 1
                        if attempt == max_retries - 1:
                            raise RuntimeError("无法找到可用端口")
                        continue
                    else:
                        raise  # 其他错误直接抛出
            
        except Exception as e:
            logger.error(f"网络连接失败: {e}")
            QMessageBox.warning(self, "错误", f"连接失败: {str(e)}")
        finally:
            self.progress_bar.hide()
    
    def on_connection_status_changed(self, connected):
        """处理连接状态变化"""
        if connected:
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("color: #2ecc71;")  # 使用更柔和的绿色
            # 再次刷新联系人列表以确保最新状态
            print("Reloading contacts after connection status change")
            self.contact_list.load_contacts()
        else:
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("color: #e74c3c;")  # 使用更柔和的红色
    
    def on_message_received(self, message):
        """处理接收到的消息"""
        try:
            sender_id = message["sender_id"]
            
            # 延迟加载聊天窗口
            chat_widget = self.chat_widgets.get(sender_id)
            if not chat_widget:
                chat_widget = ChatWidget(sender_id)
                self.chat_widgets[sender_id] = chat_widget
                self.chat_stack.addWidget(chat_widget)
            
            # 获取聊天窗口并显示消息
            chat_widget.receive_message(message)
            
            # 如果当前不是这个聊天窗口，更新未读消息数量
            if self.chat_stack.currentWidget() != chat_widget:
                self.contact_list.update_unread_count(sender_id)
                
        except Exception as e:
            logger.error(f"Error handling received message: {e}")
    
    def closeEvent(self, event):
        """处理窗口关闭事件"""
        try:
            print("\n=== 开始应用关闭流程 ===")
            print("1. 正在获取事件循环...")
            
            # 尝试获取事件循环，如果没有则创建一个新的
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            print("2. 事件循环获取成功")
            
            print("3. 正在停止网络管理器...")
            # 运行清理任务
            if self.network_manager:
                loop.run_until_complete(self.network_manager.stop())
            print("4. 网络管理器已停止")
            
            print("5. 正在调用父类关闭事件...")
            super().closeEvent(event)
            print("6. 父类关闭事件已完成")
            print("=== 应用关闭流程完成 ===\n")
            
        except Exception as e:
            print(f"\n!!! 应用关闭过程出错 !!!")
            print(f"错误详情: {str(e)}")
            print(f"错误类型: {type(e).__name__}")
            logger.error(f"Error during shutdown: {e}", exc_info=True)
            print("正在执行应急关闭...\n")
            super().closeEvent(event)
    
    def show_main_interface(self):
        """显示主界面"""
        try:
            # 更新用户信息显示
            self.user_info_label.setText(f"Logged in as: {self.username}")
            
            # 加载联系人列表
            self.contact_list.load_contacts()
            
            # 创建默认聊天页面
            default_chat = ChatWidget(None)
            self.chat_stack.addWidget(default_chat)
            self.chat_stack.setCurrentWidget(default_chat)
            
        except Exception as e:
            logger.error(f"Error showing main interface: {e}")
            QMessageBox.warning(self, "Error", f"Failed to load interface: {str(e)}")
    
    def update_unread_counts(self):
        """更新所有联系人的未读消息数"""
        try:
            if hasattr(self, 'contact_list'):
                self.contact_list.load_contacts()
        except Exception as e:
            logger.error(f"Error updating unread counts: {e}")
    
    def update_friend_list(self):
        """更新好友列表显示"""
        try:
            from src.utils.database import get_friend_list
            friends = get_friend_list(self.network_manager.user_id)
            
            # 清空当前显示
            self.friend_list.clear()
            
            # 添加好友列表
            for friend in friends:
                self.friend_list.append(
                    f"ID: {friend['id']} - {friend['username']}"
                )
                
        except Exception as e:
            logger.error(f"Error updating friend list: {e}") 