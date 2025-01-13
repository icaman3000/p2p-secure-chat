"""事件处理模块"""
from .network import network_manager
from .database import save_message

def setup_handlers():
    """设置所有事件处理器"""
    def handle_message_received(message):
        """处理接收到的消息并保存到数据库"""
        save_message(
            sender_id=message["sender_id"],
            recipient_id=message["recipient_id"],
            content=message["content"],
            timestamp=message["timestamp"]
        )

    # 连接信号
    network_manager.message_received.connect(handle_message_received) 