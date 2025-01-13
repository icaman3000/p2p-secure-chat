from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLineEdit, QPushButton
from PyQt6.QtCore import Qt
from src.utils.crypto import encrypt_message, decrypt_message
from src.utils.network import network_manager
from src.utils.database import get_user_by_id, save_message
from datetime import datetime
import asyncio

class ChatWidget(QWidget):
    def __init__(self, contact_id):
        super().__init__()
        self.contact_id = contact_id
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 聊天记录显示区域
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        layout.addWidget(self.chat_display)
        
        # 消息输入区域
        self.message_input = QLineEdit()
        self.message_input.returnPressed.connect(self.send_message)
        layout.addWidget(self.message_input)
        
        # 发送按钮
        send_button = QPushButton("Send")
        send_button.clicked.connect(self.send_message)
        layout.addWidget(send_button)
    
    def format_message(self, sender_name, message, timestamp=None):
        """格式化消息显示"""
        if timestamp:
            time_str = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{time_str}] {sender_name}: {message}"
    
    def send_message(self):
        if not self.contact_id:
            return
        
        message = self.message_input.text()
        if not message:
            return
        
        try:
            # 获取当前时间戳
            timestamp = datetime.utcnow().isoformat()
            
            # 加密消息
            encrypted_data = encrypt_message(message, self.contact_id)
            
            # 保存消息到数据库
            save_message(
                sender_id=network_manager.user_id,
                recipient_id=self.contact_id,
                content=encrypted_data,
                timestamp=timestamp
            )
            
            # 发送消息
            asyncio.create_task(self._send_message_async({
                "type": "message",
                "sender_id": network_manager.user_id,
                "recipient_id": self.contact_id,
                "content": encrypted_data,
                "timestamp": timestamp
            }))
            
            # 显示发送的消息
            formatted_message = self.format_message("Me", message, timestamp)
            self.chat_display.append(formatted_message)
            self.message_input.clear()
            
        except Exception as e:
            print(f"Send message error: {str(e)}")
    
    async def _send_message_async(self, message_data):
        """异步发送消息"""
        try:
            await network_manager.send_message(message_data)
        except Exception as e:
            print(f"Error sending message: {str(e)}")
    
    def receive_message(self, message):
        try:
            print(f"Receiving message in chat widget: {message}")  # 调试信息
            
            # 解密消息
            decrypted_message = message["content"]  # 消息已经在 NetworkManager 中解密
            
            # 获取发送者信息
            sender_id = message['sender_id']
            sender = get_user_by_id(sender_id)
            sender_name = sender.username if sender else f"User {sender_id}"
            
            # 保存接收到的消息
            save_message(
                sender_id=sender_id,
                recipient_id=network_manager.user_id,
                content={"message": decrypted_message},  # 已解密的消息不需要再加密
                timestamp=message.get("timestamp")
            )
            
            # 显示接收到的消息
            formatted_message = self.format_message(
                sender_name,
                decrypted_message,
                message.get("timestamp")
            )
            self.chat_display.append(formatted_message)
            
        except Exception as e:
            print(f"Error displaying message: {str(e)}")
            print(f"Message data: {message}")  # 打印完整的消息数据以便调试 