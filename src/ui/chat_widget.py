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
        # 完全清空聊天显示区域
        self.clear_chat_display()
        # 加载聊天历史记录
        self.load_chat_history()
    
    def clear_chat_display(self):
        """完全清空聊天显示区域"""
        if hasattr(self, 'chat_display'):
            self.chat_display.clear()
            self.chat_display.setPlainText("")  # 确保完全清空
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 聊天记录显示区域
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.clear_chat_display()  # 确保显示区域是空的
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
    
    def load_chat_history(self):
        """加载聊天历史记录"""
        if not self.contact_id or not network_manager.user_id:
            return
            
        try:
            messages = get_messages_between_users(network_manager.user_id, self.contact_id)
            contact = get_user_by_id(self.contact_id)
            
            if isinstance(contact, dict):
                contact_name = contact['username']
            else:
                contact_name = contact.username
            
            for msg in messages:
                try:
                    # 获取发送者名称
                    sender_name = "Me" if msg['sender_id'] == network_manager.user_id else contact_name
                    
                    # 获取消息内容
                    content = msg['content']
                    
                    # 如果消息是加密的，尝试解密
                    if msg.get('encryption_key'):
                        try:
                            encrypted_data = {
                                'message': content,
                                'key': msg['encryption_key']
                            }
                            # 使用接收者的ID来解密
                            decryption_user_id = msg['recipient_id']
                            content = decrypt_message(encrypted_data, decryption_user_id)
                            print(f"Successfully decrypted message: {content}")
                        except Exception as e:
                            print(f"Error decrypting message: {e}")
                            continue  # 解密失败时跳过这条消息
                    
                    # 如果内容看起来是base64编码的加密消息，跳过显示
                    if isinstance(content, str) and content.startswith('Z0FBQUFB'):
                        print(f"Skipping encrypted message content")
                        continue
                    
                    # 格式化并显示消息
                    formatted_message = self.format_message(
                        sender_name,
                        content,
                        msg['timestamp'].isoformat() if isinstance(msg['timestamp'], datetime) else msg['timestamp']
                    )
                    self.chat_display.append(formatted_message)
                    
                except Exception as e:
                    print(f"Error processing message {msg.get('id')}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error loading chat history: {e}")
    
    def send_message(self):
        """发送消息"""
        if not self.contact_id:
            return
            
        content = self.message_input.text().strip()
        if not content:
            return
            
        try:
            # 清空输入框
            self.message_input.clear()
            
            # 异步发送消息
            asyncio.create_task(network_manager.send_message(self.contact_id, content))
            
            # 立即在本地显示消息
            formatted_message = self.format_message(
                "Me",
                content,
                datetime.now().isoformat()
            )
            self.chat_display.append(formatted_message)
            
        except Exception as e:
            print(f"Error sending message: {e}")
    
    def receive_message(self, message):
        """接收消息"""
        try:
            # 获取发送者信息
            sender = get_user_by_id(message['sender_id'])
            if not sender:
                print(f"Unknown sender: {message['sender_id']}")
                return
                
            # 获取消息内容
            content = message['content']
            
            # 如果内容看起来是base64编码的加密消息，不显示
            if isinstance(content, str) and content.startswith('Z0FBQUFB'):
                print("Skipping encrypted message content")
                return
                
            # 格式化并显示消息
            formatted_message = self.format_message(
                sender['username'] if isinstance(sender, dict) else sender.username,
                content,
                message.get('timestamp')
            )
            self.chat_display.append(formatted_message)
            
        except Exception as e:
            print(f"Error displaying message: {e}") 