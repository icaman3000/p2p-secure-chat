import asyncio
import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QHBoxLayout
)
from PyQt6.QtCore import Qt
from src.utils.crypto import encrypt_message, decrypt_message
from src.utils.network import network_manager
from src.utils.database import get_user_by_id, save_message, get_messages_between_users, get_session, Message

class ChatWidget(QWidget):
    def __init__(self, contact_id, network_manager=None):
        super().__init__()
        self.contact_id = contact_id
        self.network_manager = network_manager
        self.init_ui()
        self.load_chat_history()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 聊天记录显示区域
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        layout.addWidget(self.chat_display)
        
        # 消息输入区域
        input_layout = QHBoxLayout()
        
        self.message_input = QLineEdit()
        self.message_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.message_input)
        
        send_button = QPushButton("Send")
        send_button.clicked.connect(self.send_message)
        input_layout.addWidget(send_button)
        
        layout.addLayout(input_layout)
        
    def load_chat_history(self):
        """加载聊天历史记录"""
        try:
            if not self.contact_id or not self.network_manager or not self.network_manager.user_id:
                return
                
            session = get_session()
            if not session:
                return
                
            # 获取与该联系人的所有消息
            messages = session.query(Message).filter(
                ((Message.sender_id == self.network_manager.user_id) & 
                 (Message.recipient_id == self.contact_id)) |
                ((Message.sender_id == self.contact_id) & 
                 (Message.recipient_id == self.network_manager.user_id))
            ).order_by(Message.timestamp).all()
            
            # 清空显示区域
            self.chat_display.clear()
            
            # 显示消息
            for msg in messages:
                is_sent = msg.sender_id == self.network_manager.user_id
                sender_name = self.network_manager.username if is_sent else "Contact"
                self.display_message(sender_name, msg.content, msg.timestamp, is_sent)
                
        except Exception as e:
            print(f"Error loading chat history: {e}")
            
    def display_message(self, sender: str, content: str, timestamp: datetime = None, is_sent: bool = False):
        """显示一条消息"""
        try:
            if not timestamp:
                timestamp = datetime.now()
                
            # 格式化时间戳
            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            
            # 根据消息发送方设置样式
            style = "color: blue;" if is_sent else "color: green;"
            
            # 构建消息HTML
            message_html = f"""
            <div style="{style}">
                <small>{time_str}</small><br>
                <b>{sender}:</b> {content}
            </div>
            <br>
            """
            
            # 将消息添加到显示区域
            cursor = self.chat_display.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.insertHtml(message_html)
            
            # 滚动到底部
            scrollbar = self.chat_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            
        except Exception as e:
            print(f"Error displaying message: {e}")
            
    def send_message(self):
        """发送消息"""
        try:
            content = self.message_input.text().strip()
            if not content or not self.contact_id or not self.network_manager:
                return
                
            # 构建消息
            message = {
                "type": "chat",
                "content": content,
                "timestamp": datetime.now().timestamp()
            }
            
            # 创建异步任务发送消息
            asyncio.create_task(self._send_message_async(message))
            
            # 清空输入框
            self.message_input.clear()
            
        except Exception as e:
            print(f"Error sending message: {e}")
            
    async def _send_message_async(self, message: dict):
        """异步发送消息"""
        try:
            # 发送消息
            success = await self.network_manager.send_message(self.contact_id, message)
            
            if success:
                # 保存到数据库
                session = get_session()
                if session:
                    new_message = Message(
                        sender_id=self.network_manager.user_id,
                        recipient_id=self.contact_id,
                        content=message["content"],
                        timestamp=datetime.now()
                    )
                    session.add(new_message)
                    session.commit()
                
                # 显示消息
                self.display_message(
                    self.network_manager.username,
                    message["content"],
                    datetime.now(),
                    True
                )
                
        except Exception as e:
            print(f"Error sending message: {e}")
            
    async def handle_message(self, message: dict):
        """处理接收到的消息"""
        try:
            if message.get("type") == "chat":
                content = message.get("content")
                timestamp = datetime.fromtimestamp(message.get("timestamp", datetime.now().timestamp()))
                
                # 保存到数据库
                session = get_session()
                if session:
                    new_message = Message(
                        sender_id=self.contact_id,
                        recipient_id=self.network_manager.user_id,
                        content=content,
                        timestamp=timestamp
                    )
                    session.add(new_message)
                    session.commit()
                
                # 显示消息
                self.display_message("Contact", content, timestamp, False)
                
        except Exception as e:
            print(f"Error handling message: {e}") 