import pytest
from src.utils.database import (
    register_user,
    get_user_by_id,
    get_user_by_username,
    add_contact,
    get_contacts,
    save_message,
    get_messages,
    get_unread_message_counts,
    User,
    Contact,
    Message
)

@pytest.fixture
def test_user(test_session):
    """创建测试用户"""
    user = register_user("test_user", test_session)
    test_session.commit()
    return user

@pytest.fixture
def test_contact(test_session):
    """创建测试联系人"""
    contact = register_user("test_contact", test_session)
    test_session.commit()
    return contact

def test_register_user(test_session):
    """测试用户注册"""
    username = "test_user1"
    user = register_user(username, test_session)
    test_session.commit()
    
    assert user is not None
    assert user.username == username
    
    # 测试重复用户名
    with pytest.raises(ValueError):
        register_user(username, test_session)

def test_get_user(test_session):
    """测试用户查询"""
    username = "test_user2"
    user = register_user(username, test_session)
    test_session.commit()
    
    # 通过ID查询
    found_user = get_user_by_id(user.id, test_session)
    assert found_user is not None
    assert found_user.username == username
    
    # 通过用户名查询
    found_user = get_user_by_username(username, test_session)
    assert found_user is not None
    assert found_user.id == user.id

def test_add_contact(test_session, test_user, test_contact):
    """测试添加联系人"""
    # 添加联系人
    contact = add_contact(test_user.id, test_contact.username, test_session)
    test_session.commit()
    
    assert contact is not None
    
    # 验证联系人关系
    contacts = get_contacts(test_user.id, test_session)
    assert len(contacts) == 1
    assert contacts[0]["id"] == test_contact.id

def test_message_handling(test_session, test_user, test_contact):
    """测试消息处理"""
    # 先建立联系人关系
    add_contact(test_user.id, test_contact.username, test_session)
    test_session.commit()
    
    # 发送消息
    message_content = {"text": "Hello, world!"}
    saved_message = save_message(
        sender_id=test_user.id,
        recipient_id=test_contact.id,
        content=message_content,
        session=test_session
    )
    test_session.commit()
    
    # 获取消息
    messages = get_messages(test_user.id, test_contact.id, test_session)
    assert len(messages) > 0
    assert messages[0]["content"]["text"] == "Hello, world!"
    
    # 检查未读消息数
    unread_counts = get_unread_message_counts(test_contact.id, test_session)
    assert unread_counts.get(test_user.id, 0) > 0

def test_invalid_contact_operations(test_session, test_user):
    """测试无效的联系人操作"""
    # 测试添加不存在的用户
    with pytest.raises(ValueError):
        add_contact(test_user.id, "nonexistent_user", test_session)
    
    # 测试自己添加自己
    with pytest.raises(ValueError):
        add_contact(test_user.id, test_user.username, test_session)

def test_duplicate_contact(test_session, test_user, test_contact):
    """测试重复添加联系人"""
    # 第一次添加
    contact1 = add_contact(test_user.id, test_contact.username, test_session)
    test_session.commit()
    assert contact1 is not None
    
    # 尝试重复添加
    contact2 = add_contact(test_user.id, test_contact.username, test_session)
    test_session.commit()
    assert contact2 is not None
    assert contact1.id == contact2.id  # 应该返回相同的联系人记录 