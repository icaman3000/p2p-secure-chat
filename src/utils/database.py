import os
import sys
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from src.utils.crypto import generate_keypair

# 创建数据目录
data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

# 创建数据库连接
db_path = os.path.join(data_dir, 'chat.db')
engine = create_engine(f'sqlite:///{db_path}')
Session = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    public_key = Column(String)
    private_key = Column(String)
    
    contacts = relationship('Contact', foreign_keys='Contact.user_id', back_populates='user')
    sent_friend_requests = relationship('FriendRequest', foreign_keys='FriendRequest.sender_id', back_populates='sender')
    received_friend_requests = relationship('FriendRequest', foreign_keys='FriendRequest.recipient_id', back_populates='recipient')
    sent_messages = relationship('Message', foreign_keys='Message.sender_id', back_populates='sender')
    received_messages = relationship('Message', foreign_keys='Message.recipient_id', back_populates='recipient')

class Contact(Base):
    __tablename__ = 'contacts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    contact_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    user = relationship('User', foreign_keys=[user_id], back_populates='contacts')
    contact = relationship('User', foreign_keys=[contact_id])
    
    __table_args__ = (
        UniqueConstraint('user_id', 'contact_id', name='uq_user_contact'),
    )

class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    recipient_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    content = Column(String, nullable=False)
    encryption_key = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_delivered = Column(Boolean, default=False)
    
    sender = relationship('User', foreign_keys=[sender_id], back_populates='sent_messages')
    recipient = relationship('User', foreign_keys=[recipient_id], back_populates='received_messages')
    
    __table_args__ = (
        Index('idx_messages_sender_recipient', sender_id, recipient_id),
    )

class FriendRequest(Base):
    __tablename__ = 'friend_requests'
    
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    recipient_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    status = Column(String, default='pending')  # pending, accepted, rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    
    sender = relationship('User', foreign_keys=[sender_id], back_populates='sent_friend_requests')
    recipient = relationship('User', foreign_keys=[recipient_id], back_populates='received_friend_requests')
    
    __table_args__ = (
        UniqueConstraint('sender_id', 'recipient_id', name='uq_sender_recipient'),
    )

# 创建数据库表
Base.metadata.create_all(engine)

def register_user(username, password):
    """注册新用户"""
    session = Session()
    try:
        print(f"\n开始注册新用户: username={username}")
        # 检查用户名是否已存在
        existing_user = session.query(User).filter_by(username=username).first()
        if existing_user:
            raise ValueError("Username already exists")
            
        # 生成密钥对
        keypair = generate_keypair()
        
        # 创建新用户
        new_user = User(
            username=username,
            password=password,
            public_key=str(keypair["public"]),
            private_key=str(keypair["private"])
        )
        session.add(new_user)
        session.commit()
        print(f"用户注册成功: id={new_user.id}, username={new_user.username}")
        return new_user  # 返回整个用户对象
    except Exception as e:
        session.rollback()
        print(f"用户注册失败: {str(e)}")
        raise e
    finally:
        session.close()

def get_user_by_username(username):
    """通过用户名获取用户"""
    session = Session()
    try:
        user = session.query(User).filter_by(username=username).first()
        return user
    finally:
        session.close()

def get_user_by_id(user_id):
    """通过ID获取用户"""
    session = Session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        return user
    finally:
        session.close()

def verify_user(username, password):
    """验证用户登录"""
    session = Session()
    try:
        print(f"\n尝试验证用户登录: username={username}")
        user = session.query(User).filter_by(username=username, password=password).first()
        if user:
            print(f"用户验证成功: id={user.id}, username={user.username}")
            return {'id': user.id, 'username': user.username}
        print("用户验证失败: 用户名或密码不正确")
        return None
    except Exception as e:
        print(f"用户验证出错: {str(e)}")
        return None
    finally:
        session.close()

def get_contacts(user_id):
    """获取用户的联系人列表"""
    print(f"Fetching contacts for user_id: {user_id}")
    session = Session()
    try:
        contacts = session.query(Contact).filter_by(user_id=user_id).all()
        print(f"Found {len(contacts)} contacts in database")
        
        processed_contacts = []
        for contact in contacts:
            contact_user = session.query(User).filter_by(id=contact.contact_id).first()
            if contact_user:
                print(f"Processing contact: {contact.contact_id} -> {contact_user.username}")
                processed_contacts.append({
                    'id': contact.contact_id,
                    'name': contact_user.username
                })
        
        print(f"Returning {len(processed_contacts)} processed contacts")
        return processed_contacts
    finally:
        session.close()

def add_contact(user_id, contact_username):
    """添加联系人"""
    session = Session()
    try:
        # 检查联系人是否存在
        contact_user = session.query(User).filter_by(username=contact_username).first()
        if not contact_user:
            raise ValueError("User not found")
            
        # 检查是否已经是联系人
        existing_contact = session.query(Contact).filter_by(
            user_id=user_id,
            contact_id=contact_user.id
        ).first()
        
        if existing_contact:
            raise ValueError("Already in your contact list")
            
        # 检查是否有待处理的好友请求
        existing_request = session.query(FriendRequest).filter(
            FriendRequest.sender_id == user_id,
            FriendRequest.recipient_id == contact_user.id,
            FriendRequest.status == 'pending'
        ).first()
        
        if existing_request:
            raise ValueError("Friend request already sent and pending")
            
        # 创建好友请求
        friend_request = FriendRequest(
            sender_id=user_id,
            recipient_id=contact_user.id
        )
        session.add(friend_request)
        session.commit()
        
        return {
            'request_id': friend_request.id,
            'recipient_id': contact_user.id,
            'username': contact_user.username
        }
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def handle_friend_request(request_id, user_id, accepted):
    """处理好友请求"""
    session = Session()
    try:
        # 获取好友请求
        request = session.query(FriendRequest).filter_by(id=request_id).first()
        if not request:
            raise ValueError("Friend request not found")
            
        if request.status != 'pending':
            raise ValueError("Friend request already processed")
            
        # 更新请求状态
        request.status = 'accepted' if accepted else 'rejected'
        
        if accepted:
            # 检查是否已经是联系人
            existing_contact1 = session.query(Contact).filter_by(
                user_id=request.sender_id,
                contact_id=request.recipient_id
            ).first()
            
            existing_contact2 = session.query(Contact).filter_by(
                user_id=request.recipient_id,
                contact_id=request.sender_id
            ).first()
            
            if not existing_contact1:
                # 为发送者添加联系人
                contact1 = Contact(
                    user_id=request.sender_id,
                    contact_id=request.recipient_id
                )
                session.add(contact1)
                
            if not existing_contact2:
                # 为接收者添加联系人
                contact2 = Contact(
                    user_id=request.recipient_id,
                    contact_id=request.sender_id
                )
                session.add(contact2)
                
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def get_pending_friend_requests(user_id):
    """获取待处理的好友请求"""
    session = Session()
    try:
        requests = session.query(FriendRequest).filter(
            FriendRequest.recipient_id == user_id,
            FriendRequest.status == 'pending'
        ).all()
        
        result = []
        for request in requests:
            sender = session.query(User).filter_by(id=request.sender_id).first()
            if sender:
                result.append({
                    'id': request.id,
                    'sender_id': sender.id,
                    'sender_username': sender.username,
                    'created_at': request.created_at.isoformat()
                })
        return result
    finally:
        session.close()

def save_message(sender_id, recipient_id, content, timestamp=None, encryption_key=None):
    """保存消息到数据库"""
    session = Session()
    try:
        message = Message(
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=content,
            encryption_key=encryption_key,
            timestamp=timestamp or datetime.utcnow()
        )
        session.add(message)
        session.commit()
        return {
            'id': message.id,
            'sender_id': message.sender_id,
            'recipient_id': message.recipient_id,
            'content': message.content,
            'key': message.encryption_key,
            'timestamp': message.timestamp.isoformat() if message.timestamp else None,
            'is_delivered': message.is_delivered
        }
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def get_undelivered_messages(recipient_id):
    """获取未发送的消息"""
    session = Session()
    try:
        messages = session.query(Message).filter(
            Message.recipient_id == recipient_id,
            Message.is_delivered == False
        ).all()
        
        return [{
            'id': msg.id,
            'sender_id': msg.sender_id,
            'content': msg.content,
            'key': msg.encryption_key,
            'timestamp': msg.timestamp.isoformat()
        } for msg in messages]
    finally:
        session.close()

def mark_message_as_delivered(message_id):
    """标记消息为已发送"""
    session = Session()
    try:
        message = session.query(Message).filter_by(id=message_id).first()
        if message:
            message.is_delivered = True
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def check_database_state(user_id):
    """检查数据库状态"""
    session = Session()
    try:
        print("\n=== Database State ===\n")
        
        # 检查用户信息
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            print(f"User: id={user.id}, username={user.username}\n")
            
            # 检查联系人
            contacts = session.query(Contact).filter_by(user_id=user.id).all()
            print("Contacts for user {}:".format(user.id))
            for contact in contacts:
                contact_user = session.query(User).filter_by(id=contact.contact_id).first()
                print(f"- Contact: id={contact.contact_id}, name={contact.name}, username={contact_user.username}")
            print()
            
            # 检查好友请求
            requests = session.query(FriendRequest).filter(
                (FriendRequest.sender_id == user.id) | 
                (FriendRequest.recipient_id == user.id)
            ).all()
            print("Friend Requests for user {}:".format(user.id))
            for request in requests:
                sender = session.query(User).filter_by(id=request.sender_id).first()
                print(f"- Request: id={request.id}, sender={sender.username}, recipient={user.username}, status={request.status}")
            
        print("\n===================\n")
    finally:
        session.close()

def check_messages_state():
    """检查数据库中所有消息的状态"""
    session = Session()
    try:
        messages = session.query(Message).all()
        print(f"\n数据库中的消息状态:")
        for msg in messages:
            print(f"消息ID: {msg.id}")
            print(f"发送者: {msg.sender_id}")
            print(f"接收者: {msg.recipient_id}")
            print(f"内容: {msg.content}")
            print(f"时间: {msg.timestamp}")
            print(f"已发送: {msg.is_delivered}")
            print("---")
    except Exception as e:
        print(f"检查消息状态时出错: {e}")
    finally:
        session.close()

def send_friend_request(sender_id, recipient_username):
    """发送好友请求"""
    session = Session()
    try:
        # 检查接收者是否存在
        recipient = session.query(User).filter_by(username=recipient_username).first()
        if not recipient:
            raise ValueError("User not found")
            
        # 检查是否试图添加自己
        if sender_id == recipient.id:
            raise ValueError("Cannot add yourself as a contact")
            
        # 检查是否已经是联系人
        existing_contact = session.query(Contact).filter_by(
            user_id=sender_id,
            contact_id=recipient.id
        ).first()
        
        if existing_contact:
            raise ValueError("Already in your contact list")
            
        # 检查是否有待处理的好友请求
        existing_request = session.query(FriendRequest).filter(
            FriendRequest.sender_id == sender_id,
            FriendRequest.recipient_id == recipient.id,
            FriendRequest.status == 'pending'
        ).first()
        
        if existing_request:
            raise ValueError("Friend request already sent and pending")
            
        # 创建好友请求
        friend_request = FriendRequest(
            sender_id=sender_id,
            recipient_id=recipient.id
        )
        session.add(friend_request)
        session.commit()
        
        return {
            'id': friend_request.id,
            'recipient_id': recipient.id,
            'username': recipient.username
        }
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def get_sent_friend_requests(user_id):
    """获取已发送的好友请求"""
    session = Session()
    try:
        requests = session.query(FriendRequest).filter(
            FriendRequest.sender_id == user_id,
            FriendRequest.status == 'pending'
        ).all()
        
        result = []
        for request in requests:
            recipient = session.query(User).filter_by(id=request.recipient_id).first()
            if recipient:
                result.append({
                    'id': request.id,
                    'recipient_id': recipient.id,
                    'recipient_username': recipient.username,
                    'created_at': request.created_at.isoformat()
                })
        return result
    finally:
        session.close()

def get_unread_message_counts(user_id):
    """获取每个联系人的未读消息数量"""
    session = Session()
    try:
        # 获取所有未读消息
        unread_messages = session.query(Message).filter(
            Message.recipient_id == user_id,
            Message.is_delivered == False
        ).all()
        
        # 统计每个发送者的未读消息数量
        unread_counts = {}
        for message in unread_messages:
            sender_id = message.sender_id
            if sender_id not in unread_counts:
                unread_counts[sender_id] = 0
            unread_counts[sender_id] += 1
            
        return unread_counts
    finally:
        session.close()

def mark_messages_as_read(recipient_id, sender_id):
    """将来自特定发送者的所有消息标记为已读"""
    session = Session()
    try:
        messages = session.query(Message).filter(
            Message.recipient_id == recipient_id,
            Message.sender_id == sender_id,
            Message.is_delivered == False
        ).all()
        
        for message in messages:
            message.is_delivered = True
        
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"标记消息已读时出错: {e}")
        return False
    finally:
        session.close()

if __name__ == "__main__":
    # 检查用户 222 的数据库状态
    check_database_state(2)
    check_messages_state() 