# P2P Secure Chat

一个基于P2P架构的安全聊天应用，支持端到端加密、NAT穿透和离线消息。

## 功能特性

- **P2P通信**
  - 支持NAT穿透（STUN/TURN）
  - 中继服务器作为备选连接方案
  - 自动选择最优连接路径
  - 并发消息处理

- **安全性**
  - 端到端加密
  - 消息完整性验证
  - 安全密钥交换
  - 前向安全性

- **用户体验**
  - 现代化GUI界面
  - 实时消息提醒
  - 离线消息支持
  - 联系人管理
  - 文件传输

## 技术架构

### 核心模块

- **网络层** (`src/utils/`)
  - `network.py`: 基础网络通信
  - `connection_manager.py`: P2P连接管理
  - `stun_client.py`: STUN协议实现
  - `turn_client.py`: TURN协议实现
  - `relay_server.py`: 中继服务器
  - `network_test.py`: 网络测试工具

- **安全层** (`src/utils/`)
  - `crypto.py`: 加密和密钥管理
  - `database.py`: 安全数据存储

- **用户界面** (`src/ui/`)
  - `main_window.py`: 主窗口
  - `chat_widget.py`: 聊天界面
  - `contact_list.py`: 联系人列表
  - `login_widget.py`: 登录界面

- **测试模块** (`src/`)
  - `test_p2p.py`: P2P功能测试
  - `test_network.py`: 网络功能测试

### 依赖

- Python 3.8+
- PyQt5: GUI框架
- SQLite: 本地数据存储
- cryptography: 加密库
- aiohttp: 异步HTTP客户端/服务器

## 安装说明

1. 克隆仓库：
```bash
git clone https://github.com/icaman3000/p2p-secure-chat.git
cd p2p-secure-chat
```

2. 创建虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
.\venv\Scripts\activate  # Windows
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 配置环境变量：
```bash
cp .env.example .env
# 编辑.env文件，设置必要的配置项
```

## 使用方法

1. 启动应用：
```bash
python src/main.py
```

2. 首次使用需要注册账号。

3. 登录后可以：
   - 添加联系人
   - 发起聊天
   - 发送文件
   - 管理个人信息

## 开发说明

详细的开发文档请参考 [DEVELOPMENT.md](DEVELOPMENT.md)。

### 运行测试

```bash
# 运行所有测试
python -m pytest

# 运行P2P测试
python src/test_p2p.py

# 运行网络测试
python src/test_network.py
```

## 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。
