from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.fernet import Fernet
import json
import os
import base64

def generate_keypair():
    """生成RSA密钥对"""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    public_key = private_key.public_key()
    
    return {
        "private": private_key,
        "public": public_key
    }

def save_keypair(username, keypair):
    """保存密钥对到文件"""
    # 创建用户目录
    os.makedirs(f"data/users/{username}", exist_ok=True)
    
    # 保存私钥
    private_pem = keypair["private"].private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    with open(f"data/users/{username}/private.pem", "wb") as f:
        f.write(private_pem)
    
    # 保存公钥
    public_pem = keypair["public"].public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open(f"data/users/{username}/public.pem", "wb") as f:
        f.write(public_pem)

def load_keypair(username):
    """从文件加载密钥对"""
    # 加载私钥
    with open(f"data/users/{username}/private.pem", "rb") as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None
        )
    
    # 加载公钥
    with open(f"data/users/{username}/public.pem", "rb") as f:
        public_key = serialization.load_pem_public_key(f.read())
    
    return {
        "private": private_key,
        "public": public_key
    }

def encrypt_message(message, recipient_id):
    """加密消息"""
    # 生成随机对称密钥
    symmetric_key = Fernet.generate_key()
    f = Fernet(symmetric_key)
    
    # 使用对称密钥加密消息
    encrypted_message = f.encrypt(message.encode())
    
    # 加载接收者的公钥
    with open(f"data/users/{recipient_id}/public.pem", "rb") as key_file:
        recipient_key = serialization.load_pem_public_key(key_file.read())
    
    # 使用接收者的公钥加密对称密钥
    encrypted_key = recipient_key.encrypt(
        symmetric_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    # 将bytes转换为base64字符串以便JSON序列化
    return {
        "message": base64.b64encode(encrypted_message).decode('utf-8'),
        "key": base64.b64encode(encrypted_key).decode('utf-8')
    }

def decrypt_message(encrypted_data, user_id):
    """解密消息"""
    # 将base64字符串转回bytes
    encrypted_message = base64.b64decode(encrypted_data["message"].encode('utf-8'))
    encrypted_key = base64.b64decode(encrypted_data["key"].encode('utf-8'))
    
    # 使用私钥解密对称密钥
    with open(f"data/users/{user_id}/private.pem", "rb") as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None
        )
    
    symmetric_key = private_key.decrypt(
        encrypted_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    # 使用对称密钥解密消息
    f = Fernet(symmetric_key)
    decrypted_message = f.decrypt(encrypted_message)
    
    return decrypted_message.decode()

def generate_key_pair(user_id):
    """Generate a new RSA key pair for a user and save it to files."""
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    
    # Get public key
    public_key = private_key.public_key()
    
    # Create user directory if it doesn't exist
    user_dir = f"data/users/{user_id}"
    os.makedirs(user_dir, exist_ok=True)
    
    # Save private key
    with open(f"{user_dir}/private.pem", "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # Save public key
    with open(f"{user_dir}/public.pem", "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    
    return private_key, public_key 