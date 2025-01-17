from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLineEdit, QPushButton
from PyQt6.QtCore import Qt
from src.utils.crypto import encrypt_message, decrypt_message
from src.utils.network import network_manager
from src.utils.database import get_user_by_id, save_message, get_messages_between_users
from datetime import datetime
import asyncio

class ChatWidget(QWidget):
    def __init__(self, contact_id):
        super().__init__()
        self.contact_id = contact_id
        self.init_ui()
        # 加载聊天历史记录
        self.load_chat_history()
    
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
            timestamp = datetime.utcnow()
            
            # 加密消息
            encrypted_data = encrypt_message(message, self.contact_id)
            
            # 保存消息到数据库
            saved_message = save_message(
                sender_id=network_manager.user_id,
                recipient_id=self.contact_id,
                content=encrypted_data['message'],  # 保存加密后的消息内容
                encryption_key=encrypted_data['key'],  # 保存加密密钥
                timestamp=timestamp
            )
            
            # 发送消息
            asyncio.create_task(self._send_message_async({
                "type": "message",
                "sender_id": network_manager.user_id,
                "recipient_id": self.contact_id,
                "original_message": message,  # 原始消息内容
                "content": encrypted_data['message'],  # 加密后的内容
                "key": encrypted_data['key'],
                "timestamp": timestamp.isoformat()
            }))
            
            # 清空输入框
            self.message_input.clear()
            
        except Exception as e:
            print(f"Send message error: {str(e)}")
            if hasattr(e, '__cause__'):
                print(f"Caused by: {e.__cause__}")
    
    async def _send_message_async(self, message_data):
        """异步发送消息"""
        try:
            if await network_manager.send_message(message_data):
                # 消息发送成功，显示在聊天界面
                formatted_message = self.format_message(
                    "Me",
                    message_data["original_message"],  # 使用原始消息内容
                    message_data["timestamp"]
                )
                self.chat_display.append(formatted_message)
        except Exception as e:
            print(f"Error sending message: {str(e)}")
    
    def receive_message(self, message):
        try:
            print(f"Receiving message in chat widget: {message}")  # 调试信息
            
            # 获取发送者信息
            sender_id = message['sender_id']
            sender = get_user_by_id(sender_id)
            sender_name = sender.username if sender else f"User {sender_id}"
            
            # 解析时间戳
            timestamp = datetime.fromisoformat(message.get("timestamp")) if message.get("timestamp") else datetime.utcnow()
            
            # 显示接收到的消息
            formatted_message = self.format_message(
                sender_name,
                message['decrypted_content'],  # 使用NetworkManager解密后的内容
                timestamp.isoformat()
            )
            self.chat_display.append(formatted_message)
            
        except Exception as e:
            print(f"Error displaying message: {str(e)}")
            print(f"Message data: {message}") 

    def load_chat_history(self):
        """加载聊天历史记录"""
        try:
            # 获取与当前联系人的所有消息
            messages = get_messages_between_users(network_manager.user_id, self.contact_id)
            
            # 清空当前显示
            self.chat_display.clear()
            
            # 按时间顺序显示消息
            for msg in messages:
                try:
                    # 确定发送者名称
                    if msg['sender_id'] == network_manager.user_id:
                        sender_name = "Me"
                    else:
                        sender = get_user_by_id(msg['sender_id'])
                        sender_name = sender.username if sender else f"User {msg['sender_id']}"
                    
                    # 解密消息内容
                    if msg.get('encryption_key'):
                        encrypted_data = {
                            "message": msg['content'],
                            "key": msg['encryption_key']
                        }
                        content = decrypt_message(encrypted_data, network_manager.user_id)
                    else:
                        content = msg['content']
                    
                    # 格式化并显示消息
                    formatted_message = self.format_message(
                        sender_name,
                        content,
                        msg['timestamp'].isoformat() if msg['timestamp'] else None
                    )
                    self.chat_display.append(formatted_message)
                    
                except Exception as e:
                    print(f"Error processing message {msg['id']}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error loading chat history: {e}") 