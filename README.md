# P2P 安全聊天应用

这是一个去中心化的端到端加密聊天应用，每个节点既是客户端也是服务器。

## 主要特性

- 去中心化的 P2P 架构
- 端到端加密通信
- 本地用户认证
- 好友请求管理系统
- 实时消息传递
- 局域网内自动节点发现
- 深色主题界面
- SQLite 本地消息存储
- 离线消息队列
- 自动重连机制

## 系统要求

- Python 3.8 或更高版本
- PyQt6
- SQLite3
- WebSocket 支持

## 安装步骤

1. 克隆或下载项目：

   ```bash
   git clone https://github.com/icaman3000/p2p-secure-chat.git
   cd p2p-secure-chat
   ```

2. 创建并激活虚拟环境（推荐）：

   ```bash
   python -m venv .venv
   # Linux/macOS:
   source .venv/bin/activate
   # Windows:
   .venv\Scripts\activate
   ```

3. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

4. 复制环境配置文件：

   ```bash
   cp .env.example .env
   ```

5. 配置 .env 文件：

   ```env
   # 节点监听端口
   NODE_PORT=8084
   
   # 节点发现服务端口
   DISCOVERY_PORT=8085
   
   # WebSocket 服务地址
   CHAT_SERVER_URL=ws://192.168.2.3:8084/ws
   ```

   说明：
   - NODE_PORT：用于接收其他节点连接的端口
   - DISCOVERY_PORT：用于节点发现服务的端口
   - CHAT_SERVER_URL：需要设置为本机的局域网 IP 地址

## 运行应用

1. 启动应用：

   ```bash
   python src/main.py
   ```

2. 首次使用设置：
   - 注册新用户账号
   - 系统将自动生成加密密钥
   - 节点开始监听连接

3. 使用说明：
   - 通过用户名添加联系人
   - 处理收到的好友请求
   - 点击联系人开始聊天
   - 消息自动加密传输

## 安全特性

- 端到端加密通信
- 本地密钥存储
- 消息签名验证
- 无中心服务器
- 加密数据库存储

## 网络特性

- 局域网节点自动发现
- 节点间直接通信
- 离线消息存储
- 自动重连机制
- 连接状态监控
- 心跳检测机制

## 技术细节

- PyQt6 图形界面
- SQLite 数据存储
- WebSocket 通信
- JSON 消息格式
- asyncio 异步处理

## 开发说明

项目结构：

- `src/`
  - `ui/`：用户界面组件
  - `utils/`：工具模块（网络、加密、数据库）
  - `main.py`：程序入口
- `data/`
  - `db/`：SQLite 数据库
  - `keys/`：加密密钥

## 参与贡献

欢迎提交贡献！请通过 Pull Request 提交代码。

## 开源协议

本项目采用 MIT 协议开源 - 详见 LICENSE 文件。
