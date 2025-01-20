import os
import sys
import json
import asyncio
import websockets
from datetime import datetime
from sqlalchemy.orm import Session
from src.utils.database import Message, get_user_by_id, save_message, get_undelivered_messages, mark_message_as_delivered, get_session
from src.utils.crypto import encrypt_message, decrypt_message
from PyQt6.QtCore import QObject, pyqtSignal
import base64
from contextlib import contextmanager
import netifaces
import requests
import logging
from typing import Dict, List, Optional, Tuple, Any
import socket

class NetworkEnvironment:
    """网络环境类型"""
    DIRECT = "direct"              # 直接连接，可以从外部访问
    UPNP = "upnp"                 # 通过 UPnP 可以建立端口映射
    DOUBLE_NAT = "double_nat"     # 双重 NAT
    RESTRICTED = "restricted"     # 受限网络，无法建立直接连接

class NetworkAnalyzer:
    """网络环境分析器"""
    def __init__(self):
        self.local_ip = None
        self.public_ip = None
        self.gateway_ip = None
        self.upnp_available = False
        self.nat_type = None
        self.environment = None
        
    async def analyze(self) -> Dict[str, Any]:
        """分析当前网络环境"""
        print("\n=== 开始分析网络环境 ===")
        result = {}
        
        # 1. 检测本地网络
        self._analyze_local_network()
        result["local_network"] = {
            "ip": self.local_ip,
            "gateway": self.gateway_ip,
            "interfaces": self._get_network_interfaces()
        }
        
        # 2. 检测公网访问
        await self._analyze_public_access()
        result["public_access"] = {
            "ip": self.public_ip,
            "can_access_internet": bool(self.public_ip)
        }
        
        # 3. 检测 NAT 类型
        self.nat_type = await self._detect_nat_type()
        result["nat"] = {
            "type": self.nat_type,
            "is_double_nat": self._is_double_nat()
        }
        
        # 4. 检测 UPnP 可用性
        self.upnp_available = await self._check_upnp()
        result["upnp"] = {
            "available": self.upnp_available,
            "can_map_ports": self.upnp_available
        }
        
        # 5. 确定网络环境类型
        self.environment = self._determine_environment()
        result["environment"] = self.environment
        
        # 6. 生成建议的通信方法
        result["recommendations"] = self._generate_recommendations()
        
        print("\n=== 网络环境分析完成 ===")
        return result
    
    def _analyze_local_network(self):
        """分析本地网络"""
        print("\n1. 分析本地网络...")
        
        # 获取本地 IP
        interfaces = netifaces.interfaces()
        for interface in interfaces:
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr['addr']
                    if not ip.startswith('127.'):
                        self.local_ip = ip
                        print(f"找到本地 IP: {self.local_ip}")
                        break
            if self.local_ip:
                break
        
        # 获取网关 IP
        try:
            gateways = netifaces.gateways()
            default_gateway = gateways.get('default', {}).get(netifaces.AF_INET)
            if default_gateway:
                self.gateway_ip = default_gateway[0]
                print(f"找到网关 IP: {self.gateway_ip}")
        except Exception as e:
            print(f"获取网关 IP 失败: {e}")
    
    def _get_network_interfaces(self) -> List[Dict[str, Any]]:
        """获取网络接口信息"""
        interfaces = []
        for iface in netifaces.interfaces():
            try:
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        interfaces.append({
                            "name": iface,
                            "ip": addr.get('addr'),
                            "netmask": addr.get('netmask'),
                            "broadcast": addr.get('broadcast')
                        })
            except Exception:
                continue
        return interfaces
    
    async def _analyze_public_access(self):
        """分析公网访问"""
        print("\n2. 分析公网访问...")
        
        # 尝试多个服务获取公网IP
        services = [
            'https://api.ipify.org?format=json',
            'https://api.myip.com',
            'https://api.ip.sb/ip',
            'https://api4.my-ip.io/ip.json'
        ]
        
        for service in services:
            try:
                print(f"尝试从 {service} 获取公网 IP...")
                response = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: requests.get(service, timeout=3)
                )
                if response.status_code == 200:
                    if service.endswith('.json'):
                        if 'ip' in response.json():
                            self.public_ip = response.json()['ip']
                        else:
                            self.public_ip = response.text.strip()
                    else:
                        self.public_ip = response.text.strip()
                    print(f"成功获取公网 IP: {self.public_ip}")
                    break
            except Exception as e:
                print(f"从 {service} 获取失败: {e}")
                continue
    
    async def _detect_nat_type(self) -> str:
        """检测 NAT 类型"""
        print("\n3. 检测 NAT 类型...")
        
        # 如果有 UPnP，尝试从路由器获取外网 IP
        router_external_ip = None
        if self.upnp_available and hasattr(self, 'upnp'):
            try:
                router_external_ip = self.upnp.get_external_ip()
                print(f"从路由器获取的外网 IP: {router_external_ip}")
            except:
                pass
        
        # 判断 NAT 类型
        if not self.public_ip:
            nat_type = "Unknown"
        elif router_external_ip and router_external_ip != self.public_ip:
            nat_type = "Double NAT"
        elif self._is_private_ip(self.public_ip):
            nat_type = "Double NAT"
        else:
            nat_type = "Single NAT"
        
        print(f"检测到的 NAT 类型: {nat_type}")
        return nat_type
    
    def _is_private_ip(self, ip: str) -> bool:
        """判断是否是内网 IP"""
        ip_parts = ip.split('.')
        if len(ip_parts) != 4:
            return False
        
        first_octet = int(ip_parts[0])
        second_octet = int(ip_parts[1])
        
        return (
            ip.startswith('10.') or
            (first_octet == 172 and 16 <= second_octet <= 31) or
            ip.startswith('192.168.')
        )
    
    def _is_double_nat(self) -> bool:
        """判断是否是双重 NAT"""
        return self.nat_type == "Double NAT"
    
    async def _check_upnp(self) -> bool:
        """检查 UPnP 是否可用"""
        print("\n4. 检查 UPnP 可用性...")
        
        if not UPNP_AVAILABLE:
            print("系统不支持 UPnP")
            return False
        
        try:
            # 尝试发现 UPnP 设备
            self.upnp = miniupnpc
            self.upnp.set_local_ip(self.local_ip)
            
            devices = self.upnp.discover()
            if devices <= 0:
                print("未找到 UPnP 设备")
                return False
            
            print("UPnP 可用")
            return True
            
        except Exception as e:
            print(f"检查 UPnP 失败: {e}")
            return False
    
    def _determine_environment(self) -> str:
        """确定网络环境类型"""
        print("\n5. 确定网络环境类型...")
        
        if not self.public_ip:
            env = NetworkEnvironment.RESTRICTED
        elif self._is_double_nat():
            if self.upnp_available:
                env = NetworkEnvironment.UPNP
            else:
                env = NetworkEnvironment.DOUBLE_NAT
        elif self.upnp_available:
            env = NetworkEnvironment.UPNP
        else:
            env = NetworkEnvironment.DIRECT
        
        print(f"网络环境类型: {env}")
        return env
    
    def _generate_recommendations(self) -> List[str]:
        """生成通信建议"""
        print("\n6. 生成通信建议...")
        recommendations = []
        
        if self.environment == NetworkEnvironment.DIRECT:
            recommendations.extend([
                "可以直接使用端口映射",
                "建议使用 TCP 直连"
            ])
        
        elif self.environment == NetworkEnvironment.UPNP:
            recommendations.extend([
                "可以使用 UPnP 进行端口映射",
                "建议配置端口转发"
            ])
        
        elif self.environment == NetworkEnvironment.DOUBLE_NAT:
            recommendations.extend([
                "处于双重 NAT 环境",
                "建议使用 STUN/TURN 服务器",
                "或配置端口转发"
            ])
        
        else:  # RESTRICTED
            recommendations.extend([
                "网络环境受限",
                "建议使用 TURN 服务器",
                "或使用中继服务器"
            ])
        
        print("建议:")
        for rec in recommendations:
            print(f"- {rec}")
        
        return recommendations

class NetworkManager(QObject):
    message_received = pyqtSignal(dict)
    connection_status_changed = pyqtSignal(bool)
    friend_request_received = pyqtSignal(dict)
    friend_response_received = pyqtSignal(dict)
    network_info_updated = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.user_id = None
        self.username = None
        self.local_ip = None
        self.public_ip = None
        self.server = None
        self.connected_peers: Dict[int, websockets.WebSocketServerProtocol] = {}
        self.heartbeat_tasks: Dict[int, asyncio.Task] = {}
        self.network_analyzer = NetworkAnalyzer()
        
        # 初始化网络（同步方式）
        self._init_network_sync()
        
    def _init_network_sync(self):
        """同步方式初始化网络基本设置"""
        print("\n=== 初始化网络 ===")
        
        # 1. 获取本地网络信息
        self._analyze_local_network()
        
        # 2. 获取公网 IP
        self._get_public_ip()
        
        # 3. 更新网络信息
        self.update_network_info()
        
        print("=== 网络初始化完成 ===\n")
    
    def _analyze_local_network(self):
        """分析本地网络"""
        print("1. 获取本地网络信息...")
        
        # 获取本地 IP
        interfaces = netifaces.interfaces()
        for interface in interfaces:
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr['addr']
                    if not ip.startswith('127.'):
                        self.local_ip = ip
                        print(f"本地 IP: {self.local_ip}")
                        break
            if self.local_ip:
                break
        
        # 获取网关 IP
        try:
            gateways = netifaces.gateways()
            default_gateway = gateways.get('default', {}).get(netifaces.AF_INET)
            if default_gateway:
                self.gateway_ip = default_gateway[0]
                print(f"网关 IP: {self.gateway_ip}")
        except Exception as e:
            print(f"获取网关 IP 失败: {e}")
    
    def _get_public_ip(self):
        """获取公网 IP"""
        print("\n=== 正在获取公网 IP ===")
        
        # 尝试多个服务获取公网IP
        services = [
            'https://api.ipify.org?format=json',
            'https://api.myip.com',
            'https://api.ip.sb/ip',
            'https://api4.my-ip.io/ip.json'
        ]
        
        for service in services:
            try:
                print(f"尝试从 {service} 获取...")
                response = requests.get(service, timeout=3)
                if response.status_code == 200:
                    if service.endswith('.json'):
                        if 'ip' in response.json():
                            self.public_ip = response.json()['ip']
                        else:
                            self.public_ip = response.text.strip()
                    else:
                        self.public_ip = response.text.strip()
                    print(f"成功获取公网 IP: {self.public_ip}")
                    break
            except Exception as e:
                print(f"从 {service} 获取失败: {e}")
                continue
        
        if not self.public_ip:
            print("警告: 无法获取公网 IP")
        
        print("=== IP 地址获取完成 ===")

    def update_network_info(self):
        """更新并发送网络信息"""
        network_info = self.get_network_info()
        self.network_info_updated.emit(network_info)
        return network_info

    def get_network_info(self) -> Dict[str, Any]:
        """获取网络信息"""
        return {
            "local_ip": self.local_ip,
            "public_ip": self.public_ip,
            "stun_results": self.network_analyzer.stun_results if hasattr(self.network_analyzer, 'stun_results') else []
        }

    async def start(self, port: int = None):
        """启动WebSocket服务器"""
        # 等待网络初始化完成
        await self.wait_for_init()
        
        if not self.user_id or not self.username:
            raise ValueError("User info not set. Call set_user_info() first.")
        
        # 如果没有指定端口，尝试从8000开始找到一个可用端口
        if port is None:
            port = 8000
            max_attempts = 100
            
            for attempt in range(max_attempts):
                try:
                    # 创建测试套接字
                    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    test_socket.settimeout(1)  # 设置超时
                    test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 允许端口重用
                    
                    try:
                        test_socket.bind(('0.0.0.0', port))
                        test_socket.listen(1)
                        test_socket.close()
                        print(f"Found available port: {port}")
                        break
                    except OSError as e:
                        print(f"Port {port} is not available: {e}")
                        port += 1
                        if attempt == max_attempts - 1:
                            raise RuntimeError("No available ports found")
                        continue
                    finally:
                        try:
                            test_socket.close()
                        except:
                            pass
                            
                except Exception as e:
                    print(f"Error testing port {port}: {e}")
                    port += 1
                    if attempt == max_attempts - 1:
                        raise RuntimeError("No available ports found")
                    continue
        
        # 尝试映射端口
        if UPNP_AVAILABLE:
            success, external_ip = self.map_port(port)
            if success:
                print(f"UPnP port mapping successful. External IP: {external_ip}, Port: {port}")
            else:
                print("Warning: Failed to map port using UPnP")
        else:
            print("Warning: UPnP is not available, running without port mapping")

        try:
            # 创建服务器
            self.server = await websockets.serve(
                self.handle_connection,
                "0.0.0.0",
                port,
                reuse_address=True  # 允许地址重用
            )
            print(f"WebSocket server started on port {port}")
            self.connection_status_changed.emit(True)
            self.update_network_info()  # 更新网络信息
            
            # 不再等待服务器关闭，而是让它在后台运行
            return True
            
        except Exception as e:
            print(f"Error starting WebSocket server: {e}")
            self.unmap_port()
            self.connection_status_changed.emit(False)
            raise  # 重新抛出异常以便上层处理

    async def stop(self):
        """停止服务器和所有连接"""
        print("=== 开始停止网络管理器 ===")
        
        # 停止所有心跳检测任务
        print(f"1. 正在停止 {len(self.heartbeat_tasks)} 个心跳检测任务...")
        for task in self.heartbeat_tasks.values():
            task.cancel()
        self.heartbeat_tasks.clear()
        print("2. 心跳检测任务已停止")
        
        # 关闭所有对等连接
        print(f"3. 正在关闭 {len(self.connected_peers)} 个对等连接...")
        for peer in self.connected_peers.values():
            await peer.close()
        self.connected_peers.clear()
        
        # 删除端口映射
        print("4. 正在清理资源...")
        self.unmap_port()
        
        # 关闭WebSocket服务器
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        print("=== 网络管理器停止完成 ===")

    async def handle_connection(self, websocket, path):
        """处理新的WebSocket连接"""
        try:
            # 等待身份验证消息
            auth_message = await websocket.recv()
            auth_data = json.loads(auth_message)
            
            if auth_data['type'] == 'auth':
                peer_id = auth_data['user_id']
                username = auth_data['username']
                
                # 保存连接
                self.connected_peers[peer_id] = websocket
                print(f"User {username} (ID: {peer_id}) connected")
                
                # 启动心跳检测
                self.heartbeat_tasks[peer_id] = asyncio.create_task(
                    self.heartbeat_check(peer_id, websocket)
                )
                
                # 处理消息
                try:
                    async for message in websocket:
                        await self.handle_message(peer_id, message)
                except websockets.exceptions.ConnectionClosed:
                    print(f"Connection with user {username} closed")
                finally:
                    # 清理连接
                    if peer_id in self.connected_peers:
                        del self.connected_peers[peer_id]
                    if peer_id in self.heartbeat_tasks:
                        self.heartbeat_tasks[peer_id].cancel()
                        del self.heartbeat_tasks[peer_id]
        except Exception as e:
            print(f"Error handling connection: {e}")

    async def handle_message(self, sender_id: int, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
            message_type = data.get('type')
            
            if message_type == 'message':
                # 保存加密消息到数据库
                message = save_message(
                    sender_id=sender_id,
                    recipient_id=self.user_id,
                    content=data['content'],  # 保存加密内容
                    encryption_key=data['key']
                )
                
                # 解密消息用于显示
                encrypted_data = {
                    'message': data['content'],
                    'key': data['key']
                }
                try:
                    decrypted_content = decrypt_message(encrypted_data, self.user_id)
                    print(f"Decrypted message from user {sender_id}: {decrypted_content}")
                    
                    # 发送解密后的消息到UI
                    self.message_received.emit({
                        'type': 'message',
                        'sender_id': sender_id,
                        'content': decrypted_content,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    
                    # 标记消息为已送达
                    mark_message_as_delivered(message['id'])
                    
                except Exception as e:
                    print(f"Error decrypting message: {e}")
            
            elif message_type == 'heartbeat':
                # 响应心跳
                await self.connected_peers[sender_id].send(json.dumps({
                    'type': 'heartbeat_ack'
                }))
            
            elif message_type == 'friend_request':
                # 处理好友请求
                self.friend_request_received.emit({
                    'sender_id': sender_id,
                    'request_id': data['request_id']
                })
            
            elif message_type == 'friend_response':
                # 处理好友请求响应
                self.friend_response_received.emit({
                    'request_id': data['request_id'],
                    'accepted': data['accepted']
                })
        
        except json.JSONDecodeError:
            print(f"Invalid JSON message from user {sender_id}")
        except Exception as e:
            print(f"Error handling message: {e}")

    async def heartbeat_check(self, peer_id: int, websocket: websockets.WebSocketServerProtocol):
        """心跳检测"""
        while True:
            try:
                await websocket.send(json.dumps({'type': 'heartbeat'}))
                await asyncio.sleep(30)  # 30秒发送一次心跳
            except websockets.exceptions.ConnectionClosed:
                print(f"Connection with peer {peer_id} closed during heartbeat")
                break
            except Exception as e:
                print(f"Error in heartbeat check for peer {peer_id}: {e}")
                break

    async def check_undelivered_messages(self):
        """检查未送达的消息"""
        try:
            messages = get_undelivered_messages(self.user_id)
            for msg in messages:
                print(f"Processing undelivered message from user {msg['sender_id']}")
                
                # 如果有加密密钥，尝试解密消息
                if not msg.get('key'):
                    print(f"Warning: No encryption key found for message {msg['id']}")
                    continue
                    
                try:
                    encrypted_data = {
                        'message': msg['content'],
                        'key': msg['key']
                    }
                    
                    # 尝试解密消息
                    try:
                        decrypted_content = decrypt_message(encrypted_data, self.user_id)
                        print(f"Successfully decrypted message: {decrypted_content}")
                        
                        # 发送消息到UI
                        self.message_received.emit({
                            'type': 'message',
                            'sender_id': msg['sender_id'],
                            'content': decrypted_content,
                            'timestamp': msg['timestamp'],
                            'encryption_key': msg['key']  # 添加加密密钥
                        })
                        
                        # 标记消息为已送达
                        mark_message_as_delivered(msg['id'])
                        print(f"Message {msg['id']} marked as delivered")
                        
                    except Exception as e:
                        print(f"Failed to decrypt message {msg['id']}: {e}")
                        continue
                        
                except Exception as e:
                    print(f"Error processing message {msg['id']}: {e}")
                    continue
                
        except Exception as e:
            print(f"Error checking undelivered messages: {e}")

    async def send_message(self, recipient_id: int, content: str):
        """发送消息"""
        try:
            # 加密消息
            encrypted_data = encrypt_message(content, recipient_id)
            
            # 保存消息到数据库
            message = save_message(
                sender_id=self.user_id,
                recipient_id=recipient_id,
                content=encrypted_data['message'],
                encryption_key=encrypted_data['key']
            )
            
            # 如果接收者在线，直接发送
            if recipient_id in self.connected_peers:
                await self.connected_peers[recipient_id].send(json.dumps({
                    'type': 'message',
                    'sender_id': self.user_id,
                    'content': encrypted_data['message'],
                    'key': encrypted_data['key']
                }))
                print(f"消息已发送给用户 {recipient_id}")
            else:
                print(f"用户 {recipient_id} 不在线，消息已保存到数据库")
            
            return message
            
        except Exception as e:
            print(f"Error sending message: {e}")
            raise e

    async def send_friend_request(self, recipient_id: int, request_id: int):
        """发送好友请求"""
        if recipient_id in self.connected_peers:
            try:
                await self.connected_peers[recipient_id].send(json.dumps({
                    'type': 'friend_request',
                    'sender_id': self.user_id,
                    'request_id': request_id
                }))
                print(f"Friend request sent to user {recipient_id}")
                return True
            except Exception as e:
                print(f"Error sending friend request: {e}")
                return False
        else:
            print(f"User {recipient_id} is offline")
            return False

    async def send_friend_response(self, request_id: int, recipient_id: int, accepted: bool):
        """发送好友请求响应"""
        if recipient_id in self.connected_peers:
            try:
                await self.connected_peers[recipient_id].send(json.dumps({
                    'type': 'friend_response',
                    'request_id': request_id,
                    'accepted': accepted
                }))
                print(f"Friend response sent to user {recipient_id}")
                return True
            except Exception as e:
                print(f"Error sending friend response: {e}")
                return False
        else:
            print(f"User {recipient_id} is offline")
            return False

    async def wait_for_init(self):
        """等待初始化完成"""
        if hasattr(self, 'init_task'):
            await self.init_task

    async def analyze_network(self):
        """异步分析网络环境"""
        network_analysis = await self.network_analyzer.analyze()
        return network_analysis

# 创建全局实例
network_manager = NetworkManager() 