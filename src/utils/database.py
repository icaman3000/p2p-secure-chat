import os
import sys
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from src.utils.crypto import generate_keypair
from sqlalchemy import or_, and_

# 创建数据目录
data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

Base = declarative_base()

# 全局变量存储系统数据库连接和当前用户的数据库连接
system_engine = None
system_session = None
current_engine = None
current_session = None

def init_system_database():
    """初始化系统数据库"""
    global system_engine, system_session
    
    # 创建系统数据目录
    system_dir = os.path.join(data_dir, 'system')
    os.makedirs(system_dir, exist_ok=True)
    
    # 创建系统数据库
    db_path = os.path.join(system_dir, 'system.db')
    system_engine = create_engine(f'sqlite:///{db_path}')
    
    # 创建数据库表
    Base.metadata.create_all(system_engine)
    
    # 创建会话
    Session = sessionmaker(bind=system_engine)
    system_session = Session()
    
    print("Initialized system database")
    return system_session

def init_database(user_id):
    """初始化指定用户的数据库"""
    global current_engine, current_session
    
    # 创建用户数据目录
    user_dir = os.path.join(data_dir, f'users/{user_id}')
    os.makedirs(user_dir, exist_ok=True)
    
    # 创建用户专属数据库
    db_path = os.path.join(user_dir, 'user.db')
    current_engine = create_engine(f'sqlite:///{db_path}')
    
    # 创建数据库表
    Base.metadata.create_all(current_engine)
    
    # 创建会话
    Session = sessionmaker(bind=current_engine)
    current_session = Session()
    
    print(f"Initialized database for user {user_id}")
    return current_session

def get_session():
    """获取当前用户的数据库会话"""
    if system_session is None:
        init_system_database()
    return system_session

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    public_key = Column(String)
    private_key = Column(String)
    
    # 关系
    devices = relationship('Device', back_populates='user')
    contacts = relationship('Contact', foreign_keys='Contact.user_id', back_populates='user')
    sent_friend_requests = relationship('FriendRequest', foreign_keys='FriendRequest.sender_id', back_populates='sender')
    received_friend_requests = relationship('FriendRequest', foreign_keys='FriendRequest.recipient_id', back_populates='recipient')
    sent_messages = relationship('Message', foreign_keys='Message.sender_id', back_populates='sender')
    received_messages = relationship('Message', foreign_keys='Message.recipient_id', back_populates='recipient')

class Device(Base):
    """设备模型"""
    __tablename__ = 'devices'
    
    id = Column(String, primary_key=True)  # 设备ID
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    last_sync = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    
    # 关系
    user = relationship('User', back_populates='devices')

class Contact(Base):
    __tablename__ = 'contacts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    contact_id = Column(Integer)  # 不再使用外键约束
    contact_username = Column(String, nullable=False)  # 存储联系人用户名
    contact_public_key = Column(String)  # 存储联系人公钥
    
    user = relationship('User', foreign_keys=[user_id], back_populates='contacts')
    
    __table_args__ = (
        UniqueConstraint('user_id', 'contact_id', name='uq_user_contact'),
    )

class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id'))  # 添加外键约束
    recipient_id = Column(Integer, ForeignKey('users.id'))  # 添加外键约束
    content = Column(String, nullable=False)
    encryption_key = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_delivered = Column(Boolean, default=False)
    
    # 定义与User表的关系
    sender = relationship('User', foreign_keys=[sender_id], back_populates='sent_messages')
    recipient = relationship('User', foreign_keys=[recipient_id], back_populates='received_messages')
    
    __table_args__ = (
        Index('idx_messages_sender_recipient', sender_id, recipient_id),
    )

class FriendRequest(Base):
    """好友请求模型"""
    __tablename__ = 'friend_requests'
    
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    recipient_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    status = Column(String, default='pending')  # pending, accepted, rejected
    created_at = Column(DateTime, default=datetime.now)
    processed_at = Column(DateTime, nullable=True)
    
    # 关系
    sender = relationship('User', foreign_keys=[sender_id], back_populates='sent_friend_requests')
    recipient = relationship('User', foreign_keys=[recipient_id], back_populates='received_friend_requests')

def register_user(username, password):
    """注册新用户"""
    session = get_session()
    try:
        # 检查用户名是否已存在
        existing_user = session.query(User).filter_by(username=username).first()
        if existing_user:
            raise ValueError("Username already exists")
        
        # 生成用户ID (使用正整数)
        user_id = int(abs(hash(username + str(datetime.utcnow().timestamp()))) % (10 ** 10))
        
        # 生成密钥对
        keypair = generate_keypair()
        
        # 创建新用户
        new_user = User(
            id=user_id,
            username=username,
            password=password,
            public_key=str(keypair["public"]),
            private_key=str(keypair["private"])
        )
        session.add(new_user)
        session.commit()
        
        print(f"用户注册成功: id={new_user.id}, username={new_user.username}")
        return new_user
    except Exception as e:
        session.rollback()
        print(f"用户注册失败: {str(e)}")
        raise e

def verify_user(username, password):
    """验证用户登录"""
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username, password=password).first()
        if user:
            return {'id': user.id, 'username': user.username}
        return None
    except Exception as e:
        print(f"用户验证失败: {str(e)}")
        return None

def add_contact(user_id, contact_username, contact_id, contact_public_key):
    """添加联系人"""
    session = get_session()
    try:
        # 检查是否已经是联系人
        existing_contact = session.query(Contact).filter_by(
            user_id=user_id,
            contact_id=contact_id
        ).first()
        
        if existing_contact:
            raise ValueError("Already in your contact list")
        
        # 创建新联系人
        contact = Contact(
            user_id=user_id,
            contact_id=contact_id,
            contact_username=contact_username,
            contact_public_key=contact_public_key
        )
        session.add(contact)
        session.commit()
        
        return {
            'id': contact.id,
            'contact_id': contact_id,
            'username': contact_username
        }
    except Exception as e:
        session.rollback()
        raise e

def get_contacts(user_id):
    """获取用户的联系人列表"""
    session = get_session()
    try:
        contacts = session.query(Contact).filter_by(user_id=user_id).all()
        return [{
            'id': c.contact_id,
            'username': c.contact_username,
            'public_key': c.contact_public_key
        } for c in contacts]
    except Exception as e:
        print(f"获取联系人列表失败: {str(e)}")
        return []

def handle_friend_request(request_id, user_id, accepted):
    """处理好友请求"""
    session = get_session()
    try:
        request = session.query(FriendRequest).filter_by(id=request_id).first()
        if not request:
            raise ValueError("Friend request not found")
            
        request.status = 'accepted' if accepted else 'rejected'
        
        if accepted:
            # 添加双向好友关系
            contact1 = Contact(
                user_id=request.recipient_id,
                contact_id=request.sender_id,
                contact_name=session.query(User).filter_by(id=request.sender_id).first().username
            )
            contact2 = Contact(
                user_id=request.sender_id,
                contact_id=request.recipient_id,
                contact_name=session.query(User).filter_by(id=request.recipient_id).first().username
            )
            session.add(contact1)
            session.add(contact2)
        
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        raise e

def get_pending_friend_requests(user_id: int) -> list:
    """获取用户的待处理好友请求"""
    try:
        session = get_session()
        requests = session.query(FriendRequest).filter(
            FriendRequest.recipient_id == user_id,
            FriendRequest.status == 'pending'
        ).all()
        
        result = []
        for request in requests:
            sender = session.query(User).filter(User.id == request.sender_id).first()
            if sender:
                result.append({
                    'id': request.id,
                    'sender_id': sender.id,
                    'sender_username': sender.username,
                    'created_at': request.created_at.strftime('%Y-%m-%d %H:%M:%S')
                })
        return result
    except Exception as e:
        logger.error(f"Error getting pending friend requests: {e}")
        return []
    finally:
        session.close()

def process_friend_request(request_id: int, accept: bool) -> tuple[bool, str]:
    """处理好友请求
    
    Args:
        request_id: 好友请求ID
        accept: 是否接受请求
        
    Returns:
        (success, message): 处理结果和消息
    """
    try:
        session = get_session()
        request = session.query(FriendRequest).filter(FriendRequest.id == request_id).first()
        
        if not request:
            return False, "Friend request not found"
            
        if request.status != 'pending':
            return False, "Friend request already processed"
            
        # 更新请求状态
        request.status = 'accepted' if accept else 'rejected'
        request.processed_at = datetime.now()
        
        # 如果接受请求，添加好友关系
        if accept:
            # 检查是否已经是好友
            existing = session.query(Contact).filter(
                ((Contact.user_id == request.sender_id) & (Contact.contact_id == request.recipient_id)) |
                ((Contact.user_id == request.recipient_id) & (Contact.contact_id == request.sender_id))
            ).first()
            
            if existing:
                return False, "Already friends"
                
            # 添加双向好友关系
            contact1 = Contact(
                user_id=request.sender_id,
                contact_id=request.recipient_id,
                created_at=datetime.now()
            )
            contact2 = Contact(
                user_id=request.recipient_id,
                contact_id=request.sender_id,
                created_at=datetime.now()
            )
            session.add(contact1)
            session.add(contact2)
            
        session.commit()
        return True, "Success"
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error processing friend request: {e}")
        return False, str(e)
    finally:
        session.close()

def save_message(sender_id, recipient_id, content, timestamp=None, encryption_key=None):
    """保存消息到数据库"""
    session = get_session()
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
    session = get_session()
    try:
        unread_counts = {}
        messages = session.query(Message).filter(
            Message.recipient_id == user_id,
            Message.is_delivered == False
        ).all()
        
        for msg in messages:
            if msg.sender_id not in unread_counts:
                unread_counts[msg.sender_id] = 0
            unread_counts[msg.sender_id] += 1
        
        return unread_counts
    finally:
        pass

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

def get_messages_between_users(user1_id, user2_id):
    """获取两个用户之间的所有消息"""
    try:
        with Session() as session:
            messages = session.query(Message).filter(
                or_(
                    and_(Message.sender_id == user1_id, Message.recipient_id == user2_id),
                    and_(Message.sender_id == user2_id, Message.recipient_id == user1_id)
                )
            ).order_by(Message.timestamp).all()
            
            return [
                {
                    'id': msg.id,
                    'sender_id': msg.sender_id,
                    'recipient_id': msg.recipient_id,
                    'content': msg.content,
                    'encryption_key': msg.encryption_key,
                    'timestamp': msg.timestamp,
                    'is_delivered': msg.is_delivered
                }
                for msg in messages
            ]
    except Exception as e:
        print(f"Error getting messages between users: {e}")
        return []

def get_user_by_id(user_id):
    """根据ID获取用户信息"""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            return {
                'id': user.id,
                'username': user.username,
                'public_key': user.public_key
            }
        return None
    except Exception as e:
        print(f"获取用户信息失败: {str(e)}")
        return None

def get_user_by_username(username):
    """根据用户名获取用户信息"""
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if user:
            return {
                'id': user.id,
                'username': user.username,
                'public_key': user.public_key
            }
        return None
    except Exception as e:
        print(f"获取用户信息失败: {str(e)}")
        return None

def add_friend(user_id: int, friend_id: int, friend_username: str):
    """添加好友关系"""
    session = get_session()
    try:
        # 检查是否已经是好友
        existing = session.query(Contact).filter_by(
            user_id=user_id,
            contact_id=friend_id
        ).first()
        
        if existing:
            return False, "Already friends"
            
        # 创建新的好友关系
        new_contact = Contact(
            user_id=user_id,
            contact_id=friend_id,
            contact_username=friend_username
        )
        session.add(new_contact)
        session.commit()
        return True, "Friend added successfully"
        
    except Exception as e:
        session.rollback()
        return False, str(e)
        
def remove_friend(user_id: int, friend_id: int):
    """删除好友关系"""
    session = get_session()
    try:
        # 删除好友关系
        contact = session.query(Contact).filter_by(
            user_id=user_id,
            contact_id=friend_id
        ).first()
        
        if contact:
            session.delete(contact)
            session.commit()
            return True, "Friend removed successfully"
        else:
            return False, "Friend not found"
            
    except Exception as e:
        session.rollback()
        return False, str(e)
        
def get_friend_list(user_id: int):
    """获取好友列表"""
    session = get_session()
    try:
        contacts = session.query(Contact).filter_by(user_id=user_id).all()
        return [
            {
                'id': contact.contact_id,
                'username': contact.contact_username
            }
            for contact in contacts
        ]
    except Exception as e:
        return []

def save_friend_request(sender_id: int, sender_username: str, recipient_id: int):
    """保存好友请求"""
    session = get_session()
    try:
        # 检查是否已经存在相同的请求
        existing = session.query(FriendRequest).filter_by(
            sender_id=sender_id,
            recipient_id=recipient_id,
            status='pending'
        ).first()
        
        if existing:
            return False, "Friend request already exists"
            
        # 检查是否已经是好友
        existing_contact = session.query(Contact).filter_by(
            user_id=sender_id,
            contact_id=recipient_id
        ).first()
        
        if existing_contact:
            return False, "Already friends"
            
        # 创建新的好友请求
        new_request = FriendRequest(
            sender_id=sender_id,
            sender_username=sender_username,
            recipient_id=recipient_id,
            status='pending'
        )
        session.add(new_request)
        session.commit()
        return True, "Friend request sent successfully"
        
    except Exception as e:
        session.rollback()
        return False, str(e)
        
def get_pending_friend_requests(user_id: int):
    """获取用户的待处理好友请求"""
    session = get_session()
    try:
        requests = session.query(FriendRequest).filter_by(
            recipient_id=user_id,
            status='pending'
        ).all()
        
        return [
            {
                'id': req.id,
                'sender_id': req.sender_id,
                'sender_username': req.sender_username,
                'created_at': req.created_at
            }
            for req in requests
        ]
    except Exception as e:
        print(f"Error getting pending friend requests: {e}")
        return []
        
def process_friend_request(request_id: int, accepted: bool):
    """处理好友请求"""
    session = get_session()
    try:
        request = session.query(FriendRequest).filter_by(id=request_id).first()
        if not request:
            return False, "Friend request not found"
            
        request.status = 'accepted' if accepted else 'rejected'
        request.processed_at = datetime.utcnow()
        
        if accepted:
            # 添加好友关系（双向）
            success1, msg1 = add_friend(
                request.recipient_id,
                request.sender_id,
                request.sender_username
            )
            
            success2, msg2 = add_friend(
                request.sender_id,
                request.recipient_id,
                get_user_by_id(request.recipient_id)['username']
            )
            
            if not (success1 and success2):
                session.rollback()
                return False, f"Failed to add friend: {msg1 or msg2}"
                
        session.commit()
        return True, "Friend request processed successfully"
        
    except Exception as e:
        session.rollback()
        return False, str(e)

def register_device(user_id: int, device_id: str) -> tuple[bool, str]:
    """注册新设备"""
    session = get_session()
    try:
        # 检查设备是否已存在
        existing_device = session.query(Device).filter_by(id=device_id).first()
        if existing_device:
            if existing_device.user_id != user_id:
                return False, "Device ID already registered to another user"
            existing_device.last_sync = datetime.now()
            existing_device.is_active = True
            session.commit()
            return True, "Device reactivated"
            
        # 检查当前活跃设备数量
        active_devices = session.query(Device).filter_by(
            user_id=user_id,
            is_active=True
        ).count()
        
        if active_devices >= 2:
            return False, "Maximum number of devices (2) reached. Please logout from another device first."
            
        # 创建新设备记录
        new_device = Device(
            id=device_id,
            user_id=user_id,
            last_sync=datetime.now(),
            is_active=True
        )
        session.add(new_device)
        session.commit()
        return True, "Device registered successfully"
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error registering device: {e}")
        return False, str(e)
    finally:
        session.close()

def deactivate_device(device_id: str) -> tuple[bool, str]:
    """停用设备"""
    session = get_session()
    try:
        device = session.query(Device).filter_by(id=device_id).first()
        if device:
            device.is_active = False
            session.commit()
            return True, "Device deactivated successfully"
        return False, "Device not found"
    except Exception as e:
        session.rollback()
        return False, str(e)
    finally:
        session.close()

def get_active_devices_count(user_id: int) -> int:
    """获取用户当前活跃设备数量"""
    session = get_session()
    try:
        return session.query(Device).filter_by(
            user_id=user_id,
            is_active=True
        ).count()
    finally:
        session.close()

def get_user_devices(user_id: int) -> list:
    """获取用户的所有活跃设备"""
    session = get_session()
    try:
        devices = session.query(Device).filter_by(
            user_id=user_id,
            is_active=True
        ).all()
        
        return [
            {
                'id': device.id,
                'last_sync': device.last_sync.strftime('%Y-%m-%d %H:%M:%S')
            }
            for device in devices
        ]
    except Exception as e:
        logger.error(f"Error getting user devices: {e}")
        return []
    finally:
        session.close()

def update_device_sync_time(device_id: str):
    """更新设备同步时间"""
    session = get_session()
    try:
        device = session.query(Device).filter_by(id=device_id).first()
        if device:
            device.last_sync = datetime.now()
            session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating device sync time: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    # 检查用户 222 的数据库状态
    check_database_state(2)
    check_messages_state() 