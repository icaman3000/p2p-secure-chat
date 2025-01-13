from src.utils.crypto import generate_key_pair

def main():
    print("正在为用户生成密钥对...")
    
    # 为用户1生成密钥
    private_key1, public_key1 = generate_key_pair(1)
    print("用户1密钥对生成成功")
    
    # 为用户2生成密钥
    private_key2, public_key2 = generate_key_pair(2)
    print("用户2密钥对生成成功")
    
if __name__ == "__main__":
    main() 