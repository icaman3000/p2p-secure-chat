# P2P安全聊天应用

这是一个去中心化的端到端加密聊天应用，每个节点既是客户端也是服务器。

## 主要特性

- 去中心化P2P架构
- 端到端加密通信
- 自动节点发现
- 动态端口分配
- 好友系统管理
- 实时消息通知
- 断线自动重连
- 消息队列机制

## 系统要求

- Python 3.8+
- PyQt6
- SQLite3
- WebSocket支持
- 网络接口支持广播

## 安装说明

1. 克隆仓库：

```bash
git clone https://github.com/your-username/p2p-secure-chat.git
cd p2p-secure-chat
```

2. 创建虚拟环境：

```bash
# Linux/macOS
python -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

3. 安装依赖：

```bash
pip install -r requirements.txt
```

## 配置说明

创建 `.env` 文件并配置以下参数：

```
NODE_PORT=8084          # 节点通信端口（自动分配）
DISCOVERY_PORT=8085     # 节点发现端口（自动分配）
CHAT_SERVER_URL=ws://your-ip:8084/ws  # WebSocket服务器地址
```

注意：

- 端口号会自动分配，无需手动设置
- 请将 `your-ip` 替换为您的实际IP地址

## 运行应用

1. 启动应用：

```bash
python src/main.py
```

2. 首次使用：

- 注册新账号
- 登录系统
- 添加联系人
- 开始聊天

## 功能说明

### 网络功能

- 自动发现网络中的其他节点
- 动态端口分配，避免端口冲突
- 断线自动重连（最多5次尝试）
- 心跳检测（30秒间隔）
- 消息队列确保消息可靠传递

### 好友系统

- 发送/接收好友请求
- 好友请求状态管理
- 好友列表实时更新
- 在线状态显示

### 安全功能

- RSA密钥对自动生成
- 端到端加密通信
- 本地密钥存储
- 安全通信协议

### 用户界面

- 简洁现代的界面设计
- 未读消息提醒
- 好友请求管理界面
- 消息发送状态显示
- 网络连接状态指示

## 开发说明

### 项目结构

```
src/
├── ui/          # 用户界面模块
├── utils/       # 工具类和辅助函数
├── models/      # 数据模型
└── main.py      # 程序入口
```

### 技术栈

- PyQt6：用户界面框架
- SQLite：本地数据存储
- WebSocket：网络通信
- SQLAlchemy：数据库ORM
- cryptography：加密功能

## 贡献指南

1. Fork 项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 许可证

MIT License
