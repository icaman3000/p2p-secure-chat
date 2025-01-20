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

# 尝试导入 miniupnpc，如果不可用则尝试使用系统库
try:
    import miniupnpc
    UPNP_AVAILABLE = True
    print("UPnP support is available (Python package)")
except ImportError:
    try:
        # 尝试使用系统安装的 miniupnpc
        import ctypes
        import os
        
        # 在不同的路径尝试加载库
        lib_paths = [
            '/opt/homebrew/lib/libminiupnpc.dylib',  # Homebrew ARM64
            '/usr/local/lib/libminiupnpc.dylib',     # Homebrew Intel
            '/usr/lib/libminiupnpc.dylib',           # System
        ]
        
        class MiniUPnPc:
            def __init__(self, lib_path):
                self.lib = ctypes.CDLL(lib_path)
                
                # 设置函数参数和返回类型
                self.lib.upnpDiscover.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
                self.lib.upnpDiscover.restype = ctypes.c_void_p
                
                self.lib.UPNP_GetValidIGD.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
                self.lib.UPNP_GetValidIGD.restype = ctypes.c_int
                
                self.lib.UPNP_GetExternalIPAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
                self.lib.UPNP_GetExternalIPAddress.restype = ctypes.c_int
                
                self.lib.UPNP_AddPortMapping.argtypes = [
                    ctypes.c_void_p,    # urls
                    ctypes.c_char_p,    # ext_port
                    ctypes.c_char_p,    # proto
                    ctypes.c_char_p,    # int_port
                    ctypes.c_char_p,    # int_client
                    ctypes.c_char_p,    # desc
                    ctypes.c_char_p,    # duration
                    ctypes.c_char_p     # enabled
                ]
                self.lib.UPNP_AddPortMapping.restype = ctypes.c_int
                
                self.urls = None
                self.data = None
                self.local_ip = None  # 初始化 local_ip
            
            def set_local_ip(self, ip):
                """设置本地 IP"""
                self.local_ip = ip
            
            def discover(self):
                if not self.local_ip:
                    print("错误: local_ip 未设置")
                    return 0
                    
                print("调用 upnpDiscover...")
                print("参数:")
                print(f"- 本地 IP: {self.local_ip}")
                print("- 超时时间: 5000ms")
                print("- TTL: 2")
                
                # 使用本地 IP 作为多播接口
                try:
                    multicast_addr = "239.255.255.250".encode('utf-8')  # 转换为 bytes
                    self.urls = self.lib.upnpDiscover(
                        5000,          # 超时时间 (ms)
                        None,          # 多播接口 (使用默认)
                        multicast_addr, # 多播地址 (已编码)
                        2              # TTL
                    )
                    
                    if not self.urls:
                        print("upnpDiscover 返回空")
                        print("可能的原因:")
                        print("1. 路由器未启用 UPnP 功能")
                        print("2. 路由器的 UPnP 实现不兼容")
                        print("3. 网络接口配置问题")
                        print("4. 防火墙阻止了 UPnP 发现")
                        print("\n建议:")
                        print("1. 检查路由器设置，确保 UPnP 已启用")
                        print("2. 尝试重启路由器")
                        print("3. 检查系统防火墙设置")
                        print(f"4. 在路由器管理界面搜索 '{self.local_ip}' 相关设置")
                        return 0
                    
                    print("upnpDiscover 成功，正在获取 IGD...")
                    data = ctypes.c_void_p()
                    result = self.lib.UPNP_GetValidIGD(self.urls, ctypes.byref(data))
                    
                    if result <= 0:
                        print(f"获取 IGD 失败，错误码: {result}")
                        print("错误码含义:")
                        print("0 = 未找到 IGD 设备")
                        print("-1 = 发生错误")
                        print("1 = 找到有效的已连接 IGD")
                        print("2 = 找到有效的未连接 IGD")
                        print("3 = 找到可能有效的 IGD")
                        return result
                        
                    print(f"获取 IGD 成功，状态: {result}")
                    print("IGD 状态码含义:")
                    print("1 = 已连接")
                    print("2 = 未连接")
                    print("3 = 状态未知")
                    
                    self.data = data
                    return result
                    
                except Exception as e:
                    print(f"UPnP 设备发现失败: {str(e)}")
                    print(f"异常类型: {type(e)}")
                    print(f"异常详情: {e.__dict__ if hasattr(e, '__dict__') else 'No details'}")
                    return 0
            
            def get_external_ip(self):
                if not self.urls or not self.data:
                    print("未初始化 UPnP")
                    return None
                    
                print("正在获取外网 IP...")
                ip = ctypes.create_string_buffer(16)
                result = self.lib.UPNP_GetExternalIPAddress(self.urls, ip)
                if result != 0:
                    print(f"获取外网 IP 失败，错误码: {result}")
                    return None
                    
                ip_str = ip.value.decode()
                print(f"获取外网 IP 成功: {ip_str}")
                return ip_str
            
            def add_port_mapping(self, ext_port, proto, int_port, int_client, desc):
                if not self.urls or not self.data:
                    print("未初始化 UPnP")
                    return -1
                
                print(f"正在添加端口映射: {int_client}:{int_port} -> {ext_port} ({proto})")
                try:
                    result = self.lib.UPNP_AddPortMapping(
                        self.urls,
                        str(ext_port).encode(),
                        proto.encode(),
                        str(int_port).encode(),
                        int_client.encode(),
                        desc.encode(),
                        "0".encode(),
                        "1".encode()
                    )
                    
                    if result != 0:
                        print(f"添加端口映射失败，错误码: {result}")
                        if result == 718:
                            print("端口已被映射")
                        elif result == 501:
                            print("操作被路由器拒绝")
                        elif result == 402:
                            print("无效参数")
                        elif result == 401:
                            print("未授权")
                        elif result == 500:
                            print("内部错误")
                    else:
                        print("端口映射添加成功")
                        
                    return result
                    
                except Exception as e:
                    print(f"添加端口映射时发生异常: {e}")
                    return -999
        
        # 尝试加载库
        for lib_path in lib_paths:
            if os.path.exists(lib_path):
                try:
                    miniupnpc = MiniUPnPc(lib_path)
                    UPNP_AVAILABLE = True
                    print(f"UPnP support is available (system library: {lib_path})")
                    break
                except Exception as e:
                    print(f"Failed to load {lib_path}: {e}")
        else:
            raise ImportError("No suitable miniupnpc library found")
            
    except Exception as e:
        print(f"Warning: miniupnpc not available ({e}), UPnP functionality will be disabled")
        UPNP_AVAILABLE = False

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
        self.upnp = None
        self.mapped_port = None
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
        
        # 3. 初始化 UPnP（如果可用）
        if UPNP_AVAILABLE:
            print("2. 初始化UPnP...")
            try:
                if self.setup_upnp():
                    print("UPnP初始化成功")
                else:
                    print("UPnP初始化失败")
            except Exception as e:
                print(f"UPnP初始化出错: {e}")
                self.upnp = None
        else:
            print("2. UPnP不可用，跳过初始化")
        
        # 4. 更新网络信息
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
            # 如果有 UPnP，尝试从路由器获取
            if self.upnp:
                try:
                    self.public_ip = self.upnp.get_external_ip()
                    print(f"从路由器获取到公网 IP: {self.public_ip}")
                except Exception as e:
                    print(f"从路由器获取公网 IP 失败: {e}")
        
        print("=== IP 地址获取完成 ===")

    def setup_upnp(self):
        """设置UPnP"""
        if not UPNP_AVAILABLE:
            print("UPnP support is not available (miniupnpc not installed)")
            return False
            
        try:
            print("\n=== 初始化 UPnP ===")
            print("当前状态:")
            print(f"- UPNP_AVAILABLE: {UPNP_AVAILABLE}")
            print(f"- miniupnpc 类型: {type(miniupnpc)}")
            
            self.upnp = miniupnpc
            self.upnp.set_local_ip(self.local_ip)  # 设置本地 IP
            
            print("\n1. 正在搜索 UPnP 设备...")
            devices = self.upnp.discover()
            print(f"discover() 返回值: {devices}")
            if devices <= 0:
                print("未找到 UPnP 设备")
                return False
            print(f"找到 UPnP 设备，状态码: {devices}")
            
            print("\n2. 正在获取外网 IP...")
            try:
                external_ip = self.upnp.get_external_ip()
                if external_ip:
                    print(f"外网 IP: {external_ip}")
                else:
                    print("无法获取外网 IP")
                    return False
            except Exception as e:
                print(f"获取外网 IP 失败: {str(e)}")
                return False
            
            print("\n=== UPnP 初始化成功 ===")
            return True
            
        except Exception as e:
            print(f"UPnP 设置失败: {str(e)}")
            print(f"异常类型: {type(e)}")
            print(f"异常详情: {e.__dict__ if hasattr(e, '__dict__') else 'No details'}")
            self.upnp = None
            return False

    def map_port(self, port: int) -> Tuple[bool, Optional[str]]:
        """映射端口到外网"""
        if not UPNP_AVAILABLE or not self.upnp:
            print("UPnP 不可用")
            return False, None
        
        try:
            print(f"\n=== 正在映射端口 {port} ===")
            print("当前状态:")
            print(f"- 本地 IP: {self.local_ip}")
            print(f"- UPnP 对象: {type(self.upnp)}")
            
            # 添加端口映射
            print("\n1. 添加端口映射...")
            result = self.upnp.add_port_mapping(
                port,           # 外部端口
                'TCP',         # 协议
                port,          # 内部端口
                self.local_ip, # 内部IP
                'P2P Secure Chat'  # 描述
            )
            
            if result == 0:
                self.mapped_port = port
                try:
                    external_ip = self.upnp.get_external_ip()
                    print(f"端口映射成功: {self.local_ip}:{port} -> {external_ip}:{port}")
                    print("=== 端口映射完成 ===\n")
                    return True, external_ip
                except Exception as e:
                    print(f"端口映射成功但获取外网 IP 失败: {e}")
                    return True, None
            else:
                print(f"端口映射失败，错误码: {result}")
                return False, None
            
        except Exception as e:
            print(f"端口映射失败: {str(e)}")
            print(f"异常类型: {type(e)}")
            print(f"异常详情: {e.__dict__ if hasattr(e, '__dict__') else 'No details'}")
            return False, None

    def unmap_port(self):
        """删除端口映射"""
        if not UPNP_AVAILABLE or not self.upnp or not self.mapped_port:
            return
            
        try:
            print(f"\n=== 正在删除端口 {self.mapped_port} 的映射 ===")
            # 检查端口映射是否存在
            mapping = self.upnp.getspecificportmapping(self.mapped_port, 'TCP')
            if mapping:
                # 确认是我们的映射
                if mapping[0] == self.local_ip:
                    self.upnp.deleteportmapping(self.mapped_port, 'TCP')
                    print(f"端口 {self.mapped_port} 的映射已删除")
                else:
                    print(f"端口 {self.mapped_port} 被其他应用映射，不删除")
            else:
                print(f"端口 {self.mapped_port} 没有映射")
            
            self.mapped_port = None
            print("=== 端口映射删除完成 ===\n")
            
        except Exception as e:
            print(f"删除端口映射失败: {e}")

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
            "mapped_port": self.mapped_port,
            "upnp_available": UPNP_AVAILABLE and self.upnp is not None,
            "username": self.username,
            "user_id": self.user_id
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