import pytest
from PyQt6.QtWidgets import (
    QApplication,
    QPushButton,
    QListWidgetItem,
    QMessageBox
)
from PyQt6.QtCore import Qt
from src.ui.main_window import MainWindow
from src.ui.chat_widget import ChatWidget
from src.ui.contact_list import ContactList
import asyncio

@pytest.fixture
def app(qtbot):
    """创建应用实例"""
    return QApplication.instance() or QApplication([])

@pytest.fixture
def main_window(qtbot):
    """创建主窗口实例"""
    window = MainWindow(user_id=1, username="test_user")
    qtbot.addWidget(window)
    return window

@pytest.fixture
def chat_widget(qtbot):
    """创建聊天窗口实例"""
    widget = ChatWidget(user_id=1, contact_id=1, contact_name="test_contact", network_manager=None)
    qtbot.addWidget(widget)
    return widget

@pytest.fixture
def contact_list(app, qtbot):
    """创建联系人列表实例"""
    widget = ContactList(user_id=1)  # 添加必要的参数
    qtbot.addWidget(widget)
    return widget

def test_main_window_creation(main_window):
    """测试主窗口创建"""
    assert main_window is not None
    assert main_window.user_id == 1
    assert main_window.username == "test_user"

def test_chat_widget_creation(chat_widget):
    """测试聊天窗口创建"""
    assert chat_widget is not None
    assert chat_widget.contact_id == 1
    assert chat_widget.contact_name == "test_contact"
    assert chat_widget.message_display is not None
    assert chat_widget.message_input is not None

def test_contact_list_creation(contact_list):
    """测试联系人列表创建"""
    assert contact_list is not None
    assert contact_list.list_widget is not None
    
@pytest.mark.asyncio
async def test_send_message(chat_widget, qtbot):
    """测试发送消息"""
    # 输入消息
    qtbot.keyClicks(chat_widget.message_input, "Test message")
    
    # 模拟回车键发送
    qtbot.keyClick(chat_widget.message_input, Qt.Key.Key_Return)
    await asyncio.sleep(0.1)  # 等待异步操作完成
    
    # 验证消息输入框被清空
    assert chat_widget.message_input.text() == ""

@pytest.mark.skip(reason="需要修复 QInputDialog 模拟")
def test_add_contact_dialog(contact_list, qtbot, monkeypatch):
    """测试添加联系人对话框"""
    # 模拟用户输入
    monkeypatch.setattr('PyQt6.QtWidgets.QInputDialog.getText', 
                       lambda *args: ("test_user", True))
    
    # 点击添加联系人按钮
    add_button = contact_list.findChild(QPushButton, "add_button")
    qtbot.mouseClick(add_button, Qt.MouseButton.LeftButton)

@pytest.mark.asyncio
async def test_contact_selection(contact_list, qtbot):
    """测试联系人选择"""
    signals = []
    contact_list.contact_selected.connect(lambda x: signals.append(x))
    
    # 添加测试联系人
    contact_list.add_contact(1, "Test Contact")
    
    # 模拟选择联系人
    item = contact_list.item(0)
    qtbot.mouseClick(contact_list.viewport(), Qt.MouseButton.LeftButton, pos=contact_list.visualItemRect(item).center())
    
    # 验证信号是否被触发
    assert len(signals) == 1
    assert signals[0] == 1

@pytest.mark.skip(reason="需要修复 QMessageBox 模拟")
def test_friend_request_dialog(contact_list, qtbot, monkeypatch):
    """测试好友请求对话框"""
    # 模拟好友请求
    request = {
        "id": 1,
        "sender_id": 2,
        "sender_username": "test_user",
        "timestamp": "2024-01-13T12:00:00"
    }
    
    # 模拟用户接受请求
    monkeypatch.setattr('PyQt6.QtWidgets.QMessageBox.question', 
                       lambda *args: QMessageBox.StandardButton.Yes)
    
    # 触发好友请求处理
    contact_list.handle_friend_request(request)

def test_message_display_format(chat_widget):
    """测试消息显示格式"""
    message = {
        "sender_id": 1,
        "content": {"text": "Test message"},
        "timestamp": "2024-01-13T12:00:00"
    }
    print(f"Receiving message in chat widget: {message}")
    chat_widget.receive_message(message)
    display_text = chat_widget.message_display.toPlainText()
    assert "Test message" in display_text
    assert "12:00:00" in display_text

def test_unread_message_indicator(contact_list):
    """测试未读消息指示器"""
    # 添加测试联系人
    contact_id = 1
    contact_list.add_contact(contact_id, "Test Contact")
    
    # 获取联系人项
    item = contact_list.item(0)
    assert item is not None
    assert item.text() == "Test Contact"
    
    # 更新未读消息数量
    contact_list.update_unread_count(contact_id, 1)
    
    # 验证显示更新
    updated_item = contact_list.item(0)
    assert updated_item is not None
    assert "Test Contact (1)" == updated_item.text() 