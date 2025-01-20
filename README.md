# TalkAbout

一个基于 P2P 的聊天应用。

## 特性

- 基于 WebSocket 的 P2P 通信
- 支持本地网络和 STUN 穿透
- 支持大文件传输
- 支持特殊字符和 Unicode
- 支持并发消息处理
- 美观的 Qt 用户界面
- SQLite 数据持久化

## 系统要求

- Python 3.10 或更高版本
- 支持 STUN 的网络环境
- 操作系统：Windows/macOS/Linux

## 安装

1. 克隆仓库：

```bash
git clone https://github.com/yourusername/talkabout.git
cd talkabout
```

2. 安装依赖：

```bash
poetry install
```

## 使用

1. 启动应用：

```bash
poetry run python src/main.py
```

2. 连接流程：
- 应用启动时会自动获取本地和公网 IP
- 尝试 STUN 穿透
- 建立 P2P 连接

## 开发

1. 安装开发依赖：

```bash
poetry install --with dev
```

2. 运行测试：

```bash
poetry run pytest
```

3. 代码格式化：

```bash
poetry run black .
poetry run isort .
```

## 许可证

MIT

## 贡献

欢迎提交 Issue 和 Pull Request！
