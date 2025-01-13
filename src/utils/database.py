from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, JSON, func, Enum, Index, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import enum
from .network import network_manager
from .crypto import generate_key_pair

# 创建数据库目录
os.makedirs("data/db", exist_ok=True)

# 创建数据库引擎
engine = create_engine("sqlite:///data/db/chat.db")
Session = sessionmaker(bind=engine)
Base = declarative_base()

class RequestStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True)  # 添加索引
    public_key = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 添加关系
    contacts = relationship("Contact", foreign_keys="Contact.user_id")
    received_requests = relationship("FriendRequest", foreign_keys="FriendRequest.recipient_id")

class FriendRequest(Base):
    __tablename__ = "friend_requests"
    
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id'), index=True)  # 添加外键和索引
    recipient_id = Column(Integer, ForeignKey('users.id'), index=True)  # 添加外键和索引
    status = Column(String, default=RequestStatus.PENDING.value)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 创建复合索引
    __table_args__ = (
        Index('idx_sender_recipient', sender_id, recipient_id),
    )

class Contact(Base):
    __tablename__ = "contacts"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)  # 添加外键和索引
    contact_user_id = Column(Integer, ForeignKey('users.id'), index=True)  # 添加外键和索引
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 创建复合索引
    __table_args__ = (
        Index('idx_user_contact', user_id, contact_user_id, unique=True),  # 确保不会重复添加联系人
    )

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id'), index=True)  # 添加外键和索引
    recipient_id = Column(Integer, ForeignKey('users.id'), index=True)  # 添加外键和索引
    content = Column(JSON)  # 存储加密的消息和密钥
    type = Column(String)  # sent/received
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)  # 添加索引
    is_read = Column(Boolean, default=False, index=True)  # 添加索引
    
    # 创建复合索引
    __table_args__ = (
        Index('idx_conversation', sender_id, recipient_id, timestamp),
    )

# 创建数据库表
Base.metadata.create_all(engine)

def register_user(username, session=None):
    """注册新用户"""
    should_close = False
    if session is None:
        session = Session()
        should_close = True
    try:
        # 检查用户名是否已存在
        if session.query(User).filter_by(username=username).first():
            raise ValueError("Username already exists")
        
        # 创建新用户
        user = User(
            username=username,
            public_key=""  # TODO: 添加公钥
        )
        
        session.add(user)
        session.commit()
        
        # 重新查询用户以获取完整信息
        user = session.query(User).filter_by(username=username).first()
        
        # 为用户生成密钥对
        generate_key_pair(user.id)
        
        return user
        
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if should_close:
            session.close()

def get_user_by_username(username, session=None):
    """通过用户名查找用户"""
    should_close = False
    if session is None:
        session = Session()
        should_close = True
    try:
        return session.query(User).filter_by(username=username).first()
    finally:
        if should_close:
            session.close()

def get_user_by_id(user_id, session=None):
    """通过ID查找用户"""
    should_close = False
    if session is None:
        session = Session()
        should_close = True
    try:
        return session.query(User).filter_by(id=user_id).first()
    finally:
        if should_close:
            session.close()

def get_contacts(user_id, session=None):
    """获取联系人列表"""
    should_close = False
    if session is None:
        session = Session()
        should_close = True
    try:
        contacts = session.query(Contact).filter_by(user_id=user_id).all()
        return [{"id": c.contact_user_id, "name": c.name} for c in contacts]
    finally:
        if should_close:
            session.close()

def add_contact(user_id, username, session=None):
    """添加新联系人"""
    should_close = False
    if session is None:
        session = Session()
        should_close = True
    try:
        # 查找要添加的用户
        contact_user = get_user_by_username(username, session)
        if not contact_user:
            raise ValueError("User not found")
        
        # 检查是否试图添加自己为好友
        if contact_user.id == user_id:
            raise ValueError("You cannot add yourself as a contact")
        
        # 检查联系人是否已存在
        existing = session.query(Contact).filter_by(
            user_id=user_id,
            contact_user_id=contact_user.id
        ).first()
        
        if existing:
            return existing
            
        contact = Contact(
            user_id=user_id,
            contact_user_id=contact_user.id,
            name=username
        )
        session.add(contact)
        session.commit()
        
        # 重新查询联系人以获取完整信息
        contact = session.query(Contact).filter_by(
            user_id=user_id,
            contact_user_id=contact_user.id
        ).first()
        return contact
        
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if should_close:
            session.close()

def save_message(sender_id, recipient_id, content, session=None, timestamp=None):
    """保存消息到数据库"""
    should_close = False
    if session is None:
        session = Session()
        should_close = True
    try:
        message = Message(
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=content,
            type="sent" if sender_id == network_manager.user_id else "received",
            is_read=sender_id == network_manager.user_id,  # 发送的消息默认已读
            timestamp=datetime.fromisoformat(timestamp) if timestamp else datetime.utcnow()
        )
        session.add(message)
        session.commit()
        return {
            "id": message.id,
            "type": message.type,
            "content": message.content,
            "timestamp": message.timestamp.isoformat()
        }
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if should_close:
            session.close()

def mark_messages_as_read(user_id, contact_id, session=None):
    """将与特定联系人的所有未读消息标记为已读"""
    should_close = False
    if session is None:
        session = Session()
        should_close = True
    try:
        session.query(Message).filter(
            Message.recipient_id == user_id,
            Message.sender_id == contact_id,
            Message.is_read == False
        ).update({"is_read": True})
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        if should_close:
            session.close()

def get_unread_message_counts(user_id, session=None):
    """获取每个联系人的未读消息数量"""
    should_close = False
    if session is None:
        session = Session()
        should_close = True
    try:
        result = {}
        unread_counts = session.query(
            Message.sender_id,
            func.count(Message.id)
        ).filter(
            Message.recipient_id == user_id,
            Message.is_read == False
        ).group_by(Message.sender_id).all()
        
        for sender_id, count in unread_counts:
            result[sender_id] = count
        return result
    finally:
        if should_close:
            session.close()

def get_messages(user_id, contact_id, session=None):
    """获取与特定联系人的消息历史"""
    should_close = False
    if session is None:
        session = Session()
        should_close = True
    try:
        messages = session.query(Message).filter(
            (Message.sender_id == user_id) & (Message.recipient_id == contact_id) |
            (Message.sender_id == contact_id) & (Message.recipient_id == user_id)
        ).order_by(Message.timestamp.desc()).all()
        
        return [{
            "id": m.id,
            "type": m.type,
            "content": m.content,
            "timestamp": m.timestamp.isoformat()
        } for m in messages]
    finally:
        if should_close:
            session.close()

def send_friend_request(sender_id, recipient_username):
    """发送好友请求"""
    session = Session()
    try:
        # 查找要添加的用户
        recipient = get_user_by_username(recipient_username)
        if not recipient:
            raise ValueError("User not found")
        
        # 检查是否试图添加自己为好友
        if recipient.id == sender_id:
            raise ValueError("You cannot add yourself as a contact")
        
        # 检查是否已经是好友
        existing_contact = session.query(Contact).filter_by(
            user_id=sender_id,
            contact_user_id=recipient.id
        ).first()
        
        if existing_contact:
            raise ValueError("Already in your contact list")
        
        # 检查是否已经有待处理的请求
        existing_request = session.query(FriendRequest).filter(
            FriendRequest.sender_id == sender_id,
            FriendRequest.recipient_id == recipient.id,
        ).order_by(FriendRequest.created_at.desc()).first()
        
        if existing_request:
            if existing_request.status == RequestStatus.PENDING.value:
                raise ValueError("Friend request already sent and pending")
            elif existing_request.status == RequestStatus.REJECTED.value:
                # 如果之前的请求被拒绝，允许重新发送
                request = FriendRequest(
                    sender_id=sender_id,
                    recipient_id=recipient.id
                )
                session.add(request)
                session.commit()
                return {
                    "id": request.id,
                    "recipient_id": recipient.id,
                    "recipient_username": recipient_username,
                    "status": request.status
                }
            elif existing_request.status == RequestStatus.ACCEPTED.value:
                raise ValueError("Friend request was already accepted")
        
        # 创建新的好友请求
        request = FriendRequest(
            sender_id=sender_id,
            recipient_id=recipient.id
        )
        session.add(request)
        session.commit()
        
        return {
            "id": request.id,
            "recipient_id": recipient.id,
            "recipient_username": recipient_username,
            "status": request.status
        }
        
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def handle_friend_request(request_id, recipient_id, accept=True):
    """处理好友请求"""
    session = Session()
    try:
        request = session.query(FriendRequest).filter_by(
            id=request_id,
            recipient_id=recipient_id,
            status=RequestStatus.PENDING.value
        ).first()
        
        if not request:
            raise ValueError("Friend request not found or already processed")
        
        # 更新请求状态
        request.status = RequestStatus.ACCEPTED.value if accept else RequestStatus.REJECTED.value
        
        if accept:
            # 互相添加为好友
            sender = get_user_by_id(request.sender_id)
            recipient = get_user_by_id(request.recipient_id)
            
            # 为发送者添加接收者为好友
            contact1 = Contact(
                user_id=request.sender_id,
                contact_user_id=request.recipient_id,
                name=recipient.username
            )
            
            # 为接收者添加发送者为好友
            contact2 = Contact(
                user_id=request.recipient_id,
                contact_user_id=request.sender_id,
                name=sender.username
            )
            
            session.add(contact1)
            session.add(contact2)
        
        session.commit()
        return request
        
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def get_pending_friend_requests(user_id):
    """获取用户的待处理好友请求"""
    session = Session()
    try:
        requests = session.query(FriendRequest).filter_by(
            recipient_id=user_id,
            status=RequestStatus.PENDING.value
        ).all()
        
        result = []
        for request in requests:
            sender = get_user_by_id(request.sender_id)
            result.append({
                "id": request.id,
                "sender_id": request.sender_id,
                "sender_username": sender.username if sender else "Unknown",
                "created_at": request.created_at.isoformat()
            })
        return result
    finally:
        session.close()

def get_sent_friend_requests(user_id):
    """获取用户发送的待处理好友请求"""
    session = Session()
    try:
        requests = session.query(FriendRequest).filter_by(
            sender_id=user_id,
            status=RequestStatus.PENDING.value
        ).all()
        
        result = []
        for request in requests:
            recipient = get_user_by_id(request.recipient_id)
            result.append({
                "id": request.id,
                "recipient_id": request.recipient_id,
                "recipient_username": recipient.username if recipient else "Unknown",
                "created_at": request.created_at.isoformat()
            })
        return result
    finally:
        session.close() 