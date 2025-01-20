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

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, p2p_chat, parent=None):
        super().__init__(parent)
        self.p2p_chat = p2p_chat
        self.setWindowTitle("P2P Secure Chat")
        
        # 创建中心部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 创建布局
        self.layout = QHBoxLayout(self.central_widget)
        
        # 创建并添加联系人列表
        self.contact_list = ContactList(self)
        self.layout.addWidget(self.contact_list)
        
        # 创建并添加聊天窗口
        self.chat_widget = ChatWidget(self)
        self.layout.addWidget(self.chat_widget)
        
        # 设置窗口大小
        self.resize(800, 600)
        
        # 连接信号
        self.contact_list.contact_selected.connect(self.on_contact_selected)
        
    async def connect_to_peer(self, peer_id: str, peer_addr):
        """连接到对等端"""
        return await self.p2p_chat.connect_to_peer(peer_id, peer_addr)
        
    async def send_message(self, peer_id: str, message: dict):
        """发送消息"""
        if self.p2p_chat and self.p2p_chat.manager:
            return await self.p2p_chat.manager.send_message(peer_id, message)
        return False
        
    def on_contact_selected(self, contact_id):
        """处理联系人选择事件"""
        self.chat_widget.set_current_contact(contact_id)
        
    def closeEvent(self, event):
        """处理窗口关闭事件"""
        # 确保清理P2P连接
        if self.p2p_chat:
            asyncio.create_task(self.p2p_chat.cleanup())
        super().closeEvent(event)

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
            mark_messages_as_read(network_manager.user_id, contact_id)
            self.contact_list.update_unread_count(contact_id)
            
        except Exception as e:
            logger.error(f"Error showing chat: {e}")
            QMessageBox.warning(self, "Error", f"Failed to open chat: {str(e)}")
        
        finally:
            # 隐藏加载指示器
            self.progress_bar.hide()
    
    def on_login_successful(self, user_id, username):
        """登录成功的处理函数"""
        try:
            print(f"\n用户登录成功: user_id={user_id}, username={username}")
            self.user_id = user_id
            self.username = username
            
            # 显示加载指示器
            self.progress_bar.setRange(0, 0)
            self.progress_bar.show()
            
            # 更新用户信息显示
            self.user_info_label.setText(f"当前用户: {self.username}")
            
            # 设置 network_manager 的用户信息
            network_manager.set_user_info(user_id, username)
            print("已设置 network_manager 的用户信息")
            
            # 立即加载联系人列表
            print("正在加载联系人列表...")
            contacts = self.contact_list.load_contacts()
            print(f"已加载联系人: {contacts}")
            
            # 创建默认聊天页面
            default_chat = ChatWidget(None)
            self.chat_stack.addWidget(default_chat)
            self.chat_stack.setCurrentWidget(default_chat)
            
            # 连接到网络（使用事件循环）
            loop = asyncio.get_event_loop()
            loop.create_task(self._connect_to_network())
            
        except Exception as e:
            logger.error(f"登录处理出错: {e}")
            QMessageBox.warning(self, "错误", f"初始化失败: {str(e)}")
            self.progress_bar.hide()
    
    async def _connect_to_network(self):
        """连接到网络（异步）"""
        try:
            # 尝试从8000开始，每次失败时端口号加1
            port = 8000
            max_retries = 10
            
            for attempt in range(max_retries):
                try:
                    if await network_manager.start(port):
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
    
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle('P2P Secure Chat')
        self.resize(800, 600)
        
        # 创建主布局
        layout = QVBoxLayout()
        
        # 创建堆叠窗口部件
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        
        # 创建登录窗口部件
        self.login_widget = LoginWidget()
        self.stack.addWidget(self.login_widget)
        
        # 创建联系人列表窗口部件
        self.contact_list = ContactList()
        self.stack.addWidget(self.contact_list)
        
        # 设置主布局
        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
        
        # 创建状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # 创建状态栏标签
        self.network_info_label = QLabel()
        self.statusBar.addPermanentWidget(self.network_info_label)
        
        # 更新网络信息
        self.update_network_info()
        
        # 连接信号
        self.login_widget.login_success.connect(self.on_login_success)
        
    def update_network_info(self, info):
        """更新网络信息显示"""
        if not info:
            return
            
        network_info = []
        if info.get('local_ip'):
            network_info.append(f"Local IP: {info['local_ip']}")
        if info.get('public_ip'):
            network_info.append(f"Public IP: {info['public_ip']}")
        if info.get('mapped_port'):
            network_info.append(f"Port: {info['mapped_port']}")
        if info.get('upnp_available'):
            network_info.append("UPnP: Available")
        else:
            network_info.append("UPnP: Not available")
            
        self.network_info_label.setText(" | ".join(network_info)) 