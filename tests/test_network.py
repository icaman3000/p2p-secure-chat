import pytest
import asyncio
import json
from datetime import datetime
from src.utils.network import NetworkManager

# 端口生成器
def get_test_ports():
    """生成测试用的端口对"""
    base_port = 8090
    _port = base_port
    while True:
        yield _port, _port + 1
        _port += 2

port_generator = get_test_ports()

@pytest.fixture
async def network_manager():
    """创建一个网络管理器实例用于测试"""
    manager = NetworkManager(websocket_port=8090, discovery_port=8091, user_id=1)
    try:
        await manager.start()
        yield manager
    finally:
        await manager.stop()
        await asyncio.sleep(0.1)  # Give tasks time to clean up

async def test_network_manager_start(network_manager):
    """测试网络管理器启动"""
    try:
        await network_manager.start(1, "test_user")
        assert network_manager.is_running
        assert network_manager.user_id == 1
        assert network_manager.username == "test_user"
    except Exception as e:
        pytest.fail(f"Failed to start network manager: {e}")

async def test_send_message(network_manager):
    """测试发送消息"""
    try:
        await network_manager.start(1, "test_user")
        
        # 创建测试消息
        message = {
            "type": "message",
            "content": "Hello, World!",
            "recipient_id": 2
        }
        
        # 发送消息
        success = await network_manager.send_message(2, message)
        assert success
        
        # 检查消息队列
        assert len(network_manager.message_queue) == 1
        queued_message = network_manager.message_queue[0]
        assert queued_message["type"] == "message"
        assert queued_message["content"] == message["content"]
        assert queued_message["recipient_id"] == 2
        
    except Exception as e:
        pytest.fail(f"Failed to send message: {e}")

async def test_friend_request(network_manager):
    """测试发送好友请求"""
    try:
        await network_manager.start(1, "test_user")
        
        # 发送好友请求
        success = await network_manager.send_friend_request(2)
        assert success
        
        # 检查消息队列
        assert len(network_manager.message_queue) == 1
        request = network_manager.message_queue[0]
        assert request["type"] == "friend_request"
        assert request["sender_id"] == 1
        assert request["recipient_id"] == 2
        
    except Exception as e:
        pytest.fail(f"Failed to send friend request: {e}")

async def test_friend_response(network_manager):
    """测试处理好友请求响应"""
    try:
        await network_manager.start(1, "test_user")
        
        # 发送好友请求响应
        success = await network_manager.handle_friend_response(2, True)
        assert success
        
        # 检查消息队列
        assert len(network_manager.message_queue) == 1
        response = network_manager.message_queue[0]
        assert response["type"] == "friend_response"
        assert response["sender_id"] == 1
        assert response["recipient_id"] == 2
        assert response["accepted"] == True
        
    except Exception as e:
        pytest.fail(f"Failed to handle friend response: {e}")

async def test_reconnection(network_manager):
    """测试重连机制"""
    try:
        await network_manager.start(1, "test_user")
        
        # 模拟断开连接
        await network_manager.handle_peer_disconnect(2)
        
        # 检查重连尝试次数
        assert 2 in network_manager.reconnect_attempts
        assert network_manager.reconnect_attempts[2] == 1
        
    except Exception as e:
        pytest.fail(f"Failed to test reconnection: {e}")

async def test_message_queue(network_manager):
    """测试消息队列"""
    try:
        await network_manager.start(1, "test_user")
        
        # 发送多条消息
        messages = [
            {"type": "message", "content": f"Message {i}", "recipient_id": 2}
            for i in range(3)
        ]
        
        for message in messages:
            await network_manager.send_message(2, message)
            
        # 检查消息队列
        assert len(network_manager.message_queue) == 3
        for i, queued_message in enumerate(network_manager.message_queue):
            assert queued_message["type"] == "message"
            assert queued_message["content"] == f"Message {i}"
            assert queued_message["recipient_id"] == 2
            
    except Exception as e:
        pytest.fail(f"Failed to test message queue: {e}")

async def test_stop(network_manager):
    """测试停止网络管理器"""
    try:
        await network_manager.start(1, "test_user")
        await network_manager.stop()
        
        assert not network_manager.is_running
        assert not network_manager.server
        
    except Exception as e:
        pytest.fail(f"Failed to stop network manager: {e}")

async def test_disconnect(network_manager):
    """测试断开连接"""
    try:
        await network_manager.start(1, "test_user")
        await network_manager.disconnect()
        
        assert not network_manager.is_running
        assert not network_manager.connected_peers
        
    except Exception as e:
        pytest.fail(f"Failed to disconnect: {e}")

async def test_heartbeat(network_manager):
    """测试心跳检测"""
    try:
        await network_manager.start(1, "test_user")
        
        # 添加一个测试节点
        network_manager.connected_peers[2] = None
        network_manager.last_heartbeat[2] = datetime.now().timestamp() - 100
        
        # 等待心跳检测
        await asyncio.sleep(1)
        
        # 检查节点是否被移除
        assert 2 not in network_manager.connected_peers
        
    except Exception as e:
        pytest.fail(f"Failed to test heartbeat: {e}")

async def test_invalid_message(network_manager):
    """测试处理无效消息"""
    try:
        await network_manager.start(1, "test_user")
        
        # 发送无效消息
        invalid_message = {"type": "invalid"}
        await network_manager.handle_message(invalid_message)
        
        # 确保没有异常抛出
        assert True
        
    except Exception as e:
        pytest.fail(f"Failed to handle invalid message: {e}")

async def test_connection_error(network_manager):
    """测试连接错误处理"""
    try:
        await network_manager.start(1, "test_user")
        
        # 尝试连接到不存在的节点
        success = await network_manager.connect_to_peer(999)
        assert not success
        
    except Exception as e:
        pytest.fail(f"Failed to handle connection error: {e}")

async def test_multiple_messages(network_manager):
    """测试发送多条消息"""
    try:
        await network_manager.start(1, "test_user")
        
        # 发送多条消息给不同的接收者
        recipients = [2, 3, 4]
        for recipient_id in recipients:
            message = {
                "type": "message",
                "content": f"Message for {recipient_id}",
                "recipient_id": recipient_id
            }
            await network_manager.send_message(recipient_id, message)
            
        # 检查消息队列
        assert len(network_manager.message_queue) == len(recipients)
        for i, message in enumerate(network_manager.message_queue):
            assert message["type"] == "message"
            assert message["recipient_id"] == recipients[i]
            assert message["content"] == f"Message for {recipients[i]}"
            
    except Exception as e:
        pytest.fail(f"Failed to send multiple messages: {e}")

@pytest.mark.asyncio
async def test_concurrent_operations(network_manager):
    """测试并发操作"""
    try:
        await network_manager.start(1, "test_user")
        
        # 创建多个并发任务
        tasks = []
        for i in range(5):
            tasks.append(asyncio.create_task(
                network_manager.send_message(2, f"Message {i}")
            ))
            
        # 等待所有任务完成
        results = await asyncio.gather(*tasks)
        
        # 验证所有任务都成功完成
        assert all(results)
        
        await network_manager.stop()
    except Exception as e:
        pytest.fail(f"Failed to handle concurrent operations: {e}")

async def test_cleanup(network_manager):
    """测试清理操作"""
    try:
        await network_manager.start(1, "test_user")
        
        # 添加一些测试数据
        network_manager.connected_peers[2] = None
        network_manager.message_queue.append({"type": "test"})
        
        # 停止服务
        await network_manager.stop()
        
        # 检查是否清理干净
        assert not network_manager.is_running
        assert not network_manager.connected_peers
        assert not network_manager.message_queue
        
    except Exception as e:
        pytest.fail(f"Failed to cleanup: {e}") 