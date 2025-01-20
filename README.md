# P2P Secure Chat

一个基于P2P架构的安全聊天应用，支持端到端加密和离线消息。

## 功能特性

- 🔒 端到端加密通信
- 👥 好友管理系统
  - 发送和接收好友请求
  - 支持离线好友请求
  - 好友列表管理
- 💬 即时通讯
  - 实时消息发送和接收
  - 支持离线消息存储
  - 消息历史记录
- 🌐 P2P网络
  - 本地连接支持
  - STUN服务器支持
  - 自动网络发现
- 🎨 现代化UI界面
  - 深色主题
  - 响应式设计
  - 用户友好的界面

## 系统要求

- Python 3.8+
- 支持的操作系统：Windows, macOS, Linux

## 安装说明

1. 克隆仓库：
```bash
git clone https://github.com/yourusername/p2p-secure-chat.git
cd p2p-secure-chat
```

2. 安装Poetry（如果尚未安装）：
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

3. 安装依赖：
```bash
poetry install
```

## 使用方法

1. 启动应用：
```bash
poetry run python src/main.py
```

2. 首次使用需要注册账号：
   - 点击注册按钮
   - 输入用户名和密码
   - 完成注册

3. 添加好友：
   - 在主界面输入好友的用户ID
   - 点击"添加好友"按钮
   - 等待对方接受请求

4. 开始聊天：
   - 在好友列表中选择联系人
   - 在消息输入框输入内容
   - 点击发送或按回车键

## 技术栈

- Python 3.8+
- PyQt6 - GUI框架
- SQLite - 本地数据存储
- SQLAlchemy - ORM框架
- asyncio - 异步IO
- cryptography - 加密库

## 安全特性

- 使用RSA进行密钥交换
- AES-256用于消息加密
- 本地数据库加密存储
- 安全的用户认证机制

## 配置说明

应用程序会在首次运行时自动创建必要的配置文件和数据库。配置文件位于：

- 系统数据库：`data/system/system.db`
- 用户数据：`data/users/<user_id>/user.db`
- 日志文件：`logs/`

## 贡献指南

欢迎提交Pull Request和Issue。在提交代码前，请确保：

1. 代码符合PEP 8规范
2. 添加了必要的测试
3. 更新了相关文档
4. 提交信息清晰明了

## 许可证

MIT License
