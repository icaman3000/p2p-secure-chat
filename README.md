# P2P 安全聊天应用

这是一个去中心化的端到端加密聊天应用，每个节点既是客户端也是服务器。

## 主要特性

### 核心功能

- 去中心化的 P2P 架构
- 端到端加密通信
- 本地用户认证
- 好友请求管理系统
- 实时消息传递
- 局域网内自动节点发现

### 用户界面

- 现代化的 Qt6 界面
- 深色/浅色主题切换
- 未读消息提醒
- 在线状态显示
- 消息历史记录
- 文件传输进度显示

### 网络功能

- WebSocket P2P 通信
- 自动节点发现
- 智能重连机制
- 心跳检测
- 离线消息队列
- NAT 穿透支持

### 安全特性

- 端到端加密
- 密钥自动轮换
- 消息签名验证
- 安全的密钥存储
- 加密的本地数据库
- 防重放攻击保护

## 系统要求

- Python 3.8 或更高版本
- 支持的操作系统：
  - Windows 10/11
  - macOS 10.15+
  - Linux (Ubuntu 20.04+, Debian 11+)
- 网络要求：
  - 开放的 TCP 端口（默认 8084, 8085）
  - 局域网访问权限
  - IPv4/IPv6 支持

## 快速开始

### 安装

1. 克隆项目：

   ```shell
   git clone https://github.com/icaman3000/p2p-secure-chat.git
   cd p2p-secure-chat
   ```

2. 创建虚拟环境：

   ```shell
   python -m venv .venv
   
   # Linux/macOS:
   source .venv/bin/activate
   # Windows:
   .venv\Scripts\activate
   ```

3. 安装依赖：

   ```shell
   pip install -r requirements.txt
   ```

4. 配置环境：

   ```shell
   cp .env.example .env
   # 编辑 .env 文件设置必要参数
   ```

### 配置说明

`.env` 文件配置项：

```ini
# 网络配置
CHAT_SERVER_URL=ws://192.168.2.3:8084/ws
NODE_PORT=8084
DISCOVERY_PORT=8085

# 数据库配置
DATABASE_PATH=chat.db

# 网络参数
MAX_RECONNECT_ATTEMPTS=5
HEARTBEAT_INTERVAL=30
MESSAGE_QUEUE_SIZE=100

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=app.log

# UI配置
DARK_MODE=false
CHAT_HISTORY_LIMIT=100
UNREAD_MESSAGE_INDICATOR=true

# 安全配置
ENCRYPTION_ENABLED=true
KEY_ROTATION_INTERVAL=86400  # 24小时
```

### 运行

1. 启动应用：

   ```shell
   python src/main.py
   ```

2. 首次使用：
   - 注册新账号
   - 等待节点发现服务启动
   - 添加联系人开始聊天

## 开发指南

### 项目结构

```text
src/
├── ui/                 # 用户界面组件
│   ├── main_window.py  # 主窗口
│   ├── chat_widget.py  # 聊天界面
│   └── contact_list.py # 联系人列表
├── utils/              # 工具模块
│   ├── network.py      # 网络管理
│   ├── database.py     # 数据库操作
│   ├── crypto.py       # 加密工具
│   └── discovery.py    # 节点发现
├── main.py             # 程序入口
└── __init__.py
```

### 核心模块

1. 网络管理 (`network.py`)
   - WebSocket 服务器/客户端
   - 消息队列管理
   - 连接状态监控
   - 重连机制

2. 数据库 (`database.py`)
   - SQLite 异步操作
   - 消息历史记录
   - 用户信息管理
   - 联系人管理

3. 加密模块 (`crypto.py`)
   - 端到端加密
   - 密钥管理
   - 消息签名
   - 安全存储

4. 节点发现 (`discovery.py`)
   - UDP 广播
   - 节点状态追踪
   - 地址解析
   - 心跳检测

### 测试

运行测试：

```shell
# 运行所有测试
pytest

# 运行特定模块测试
pytest tests/test_network.py

# 生成覆盖率报告
pytest --cov=src tests/
```

## 故障排除

常见问题：

1. 端口被占用

   ```shell
   # 检查端口占用
   netstat -an | grep 8084
   # 终止占用进程
   kill $(lsof -t -i:8084)
   ```

2. 节点发现失败
   - 检查防火墙设置
   - 确认局域网访问权限
   - 验证广播地址配置

3. 消息发送失败
   - 检查网络连接
   - 验证加密配置
   - 查看错误日志

## 贡献指南

1. Fork 项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 更新日志

### v1.0.0 (2024-01-13)

- 实现基础的 P2P 通信
- 添加端到端加密
- 实现好友请求系统
- 添加节点发现功能
- 优化用户界面
- 改进错误处理

## 开源协议

本项目采用 MIT 协议开源 - 详见 LICENSE 文件。
