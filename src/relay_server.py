import os
import asyncio
import logging
from dotenv import load_dotenv
from src.utils.relay_server import RelayServer

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def main():
    # 获取环境变量
    port = int(os.getenv('PORT', '8080'))
    host = os.getenv('HOST', '0.0.0.0')
    secret_key = os.getenv('SECRET_KEY', 'your-secret-key')
    
    # 创建中继服务器
    server = RelayServer(
        host=host,
        port=port,
        secret_key=secret_key
    )
    
    try:
        # 启动服务器
        await server.start()
        logging.info(f"中继服务器启动在 {host}:{port}")
        
        # 保持运行
        while True:
            await asyncio.sleep(3600)
            
    except KeyboardInterrupt:
        logging.info("正在关闭服务器...")
        await server.stop()
        
if __name__ == "__main__":
    asyncio.run(main()) 