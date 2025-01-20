import asyncio
import socket
import requests
import websockets
import json
from typing import Dict, Any
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.utils.network import NetworkManager, NetworkEnvironment

class NetworkTester:
    def __init__(self):
        self.network_manager = NetworkManager()
        self.test_results = {}
        
    async def run_all_tests(self):
        """运行所有测试"""
        print("\n=== 开始网络连通性测试 ===")
        
        # 1. 基本网络测试
        await self.test_basic_network()
        
        # 2. 端口测试
        await self.test_ports()
        
        # 3. UPnP 测试
        await self.test_upnp()
        
        # 4. 外部连接测试
        await self.test_external_connection()
        
        # 显示测试报告
        self.show_report()
        
    async def test_basic_network(self):
        """测试基本网络连通性"""
        print("\n1. 基本网络测试")
        self.test_results["basic_network"] = {}
        
        # 测试本地网络
        print("1.1 测试本地网络...")
        try:
            if self.network_manager.local_ip:
                print(f"√ 本地 IP 可用: {self.network_manager.local_ip}")
                self.test_results["basic_network"]["local_ip"] = True
            else:
                print("× 无法获取本地 IP")
                self.test_results["basic_network"]["local_ip"] = False
        except Exception as e:
            print(f"× 本地网络测试失败: {e}")
            self.test_results["basic_network"]["local_ip"] = False
        
        # 测试网关连通性
        print("\n1.2 测试网关连通性...")
        try:
            gateway = self.network_manager.gateway_ip
            if gateway:
                response = os.system(f"ping -c 1 -W 1 {gateway} > /dev/null 2>&1")
                if response == 0:
                    print(f"√ 网关可访问: {gateway}")
                    self.test_results["basic_network"]["gateway"] = True
                else:
                    print(f"× 网关无响应: {gateway}")
                    self.test_results["basic_network"]["gateway"] = False
            else:
                print("× 无法获取网关地址")
                self.test_results["basic_network"]["gateway"] = False
        except Exception as e:
            print(f"× 网关测试失败: {e}")
            self.test_results["basic_network"]["gateway"] = False
        
        # 测试互联网连接
        print("\n1.3 测试互联网连接...")
        try:
            response = requests.get("https://www.baidu.com", timeout=5)
            if response.status_code == 200:
                print("√ 互联网连接正常")
                self.test_results["basic_network"]["internet"] = True
            else:
                print(f"× 互联网连接异常: {response.status_code}")
                self.test_results["basic_network"]["internet"] = False
        except Exception as e:
            print(f"× 互联网连接测试失败: {e}")
            self.test_results["basic_network"]["internet"] = False
        
        # 测试公网 IP
        print("\n1.4 测试公网 IP...")
        if self.network_manager.public_ip:
            print(f"√ 公网 IP 可用: {self.network_manager.public_ip}")
            self.test_results["basic_network"]["public_ip"] = True
        else:
            print("× 无法获取公网 IP")
            self.test_results["basic_network"]["public_ip"] = False
    
    async def test_ports(self):
        """测试端口可用性"""
        print("\n2. 端口测试")
        self.test_results["ports"] = {}
        
        # 测试常用端口
        test_ports = [8000, 8001, 8002]
        for port in test_ports:
            print(f"\n2.1 测试端口 {port}...")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                if result == 0:
                    print(f"× 端口 {port} 已被占用")
                    self.test_results["ports"][port] = "occupied"
                else:
                    print(f"√ 端口 {port} 可用")
                    self.test_results["ports"][port] = "available"
                sock.close()
            except Exception as e:
                print(f"× 端口 {port} 测试失败: {e}")
                self.test_results["ports"][port] = "error"
    
    async def test_upnp(self):
        """测试 UPnP 功能"""
        print("\n3. UPnP 测试")
        self.test_results["upnp"] = {}
        
        # 检查 UPnP 可用性
        print("3.1 检查 UPnP 状态...")
        if self.network_manager.upnp:
            print("√ UPnP 已初始化")
            self.test_results["upnp"]["initialized"] = True
            
            # 测试端口映射
            print("\n3.2 测试端口映射...")
            test_port = 8888
            success, external_ip = self.network_manager.map_port(test_port)
            if success:
                print(f"√ 端口映射成功: {test_port} -> {external_ip}:{test_port}")
                self.test_results["upnp"]["port_mapping"] = True
                
                # 清理测试端口
                self.network_manager.unmap_port()
            else:
                print(f"× 端口映射失败")
                self.test_results["upnp"]["port_mapping"] = False
        else:
            print("× UPnP 未初始化")
            self.test_results["upnp"]["initialized"] = False
    
    async def test_external_connection(self):
        """测试外部连接"""
        print("\n4. 外部连接测试")
        self.test_results["external_connection"] = {}
        
        # 启动测试服务器
        print("4.1 启动测试服务器...")
        try:
            # 设置测试用户信息
            self.network_manager.user_id = -1
            self.network_manager.username = "test_user"
            
            # 启动服务器
            success = await self.network_manager.start()
            if success:
                print("√ 服务器启动成功")
                self.test_results["external_connection"]["server_start"] = True
                
                # 获取连接信息
                network_info = self.network_manager.get_network_info()
                print(f"\n连接信息:")
                print(f"- 本地地址: {network_info['local_ip']}")
                print(f"- 公网地址: {network_info['public_ip']}")
                print(f"- 映射端口: {network_info['mapped_port']}")
                print(f"- UPnP状态: {'可用' if network_info['upnp_available'] else '不可用'}")
                
                # 停止服务器
                await self.network_manager.stop()
                print("\n√ 服务器已停止")
            else:
                print("× 服务器启动失败")
                self.test_results["external_connection"]["server_start"] = False
        except Exception as e:
            print(f"× 外部连接测试失败: {e}")
            self.test_results["external_connection"]["server_start"] = False
    
    def show_report(self):
        """显示测试报告"""
        print("\n=== 网络测试报告 ===")
        
        # 1. 基本网络
        print("\n1. 基本网络状态:")
        basic = self.test_results.get("basic_network", {})
        print(f"- 本地网络: {'✓' if basic.get('local_ip') else '✗'}")
        print(f"- 网关连接: {'✓' if basic.get('gateway') else '✗'}")
        print(f"- 互联网连接: {'✓' if basic.get('internet') else '✗'}")
        print(f"- 公网 IP: {'✓' if basic.get('public_ip') else '✗'}")
        
        # 2. 端口状态
        print("\n2. 端口状态:")
        ports = self.test_results.get("ports", {})
        for port, status in ports.items():
            status_symbol = '✓' if status == 'available' else '✗'
            print(f"- 端口 {port}: {status_symbol} ({status})")
        
        # 3. UPnP 状态
        print("\n3. UPnP 状态:")
        upnp = self.test_results.get("upnp", {})
        print(f"- 初始化: {'✓' if upnp.get('initialized') else '✗'}")
        print(f"- 端口映射: {'✓' if upnp.get('port_mapping') else '✗'}")
        
        # 4. 外部连接
        print("\n4. 外部连接:")
        external = self.test_results.get("external_connection", {})
        print(f"- 服务器启动: {'✓' if external.get('server_start') else '✗'}")
        
        # 总结
        print("\n=== 测试总结 ===")
        total_tests = sum(len(v) for v in self.test_results.values())
        passed_tests = sum(
            sum(1 for v in category.values() if v is True)
            for category in self.test_results.values()
        )
        print(f"总测试项: {total_tests}")
        print(f"通过项数: {passed_tests}")
        print(f"通过率: {(passed_tests/total_tests*100):.1f}%")
        
        # 建议
        print("\n=== 改进建议 ===")
        if not basic.get('local_ip'):
            print("- 检查网络适配器配置")
        if not basic.get('gateway'):
            print("- 检查路由器连接")
        if not basic.get('internet'):
            print("- 检查互联网连接")
        if not basic.get('public_ip'):
            print("- 检查 NAT 设置")
        if not upnp.get('initialized'):
            print("- 检查路由器 UPnP 设置")
        if not upnp.get('port_mapping'):
            print("- 尝试手动配置端口转发")
        if not external.get('server_start'):
            print("- 检查防火墙设置")

async def main():
    tester = NetworkTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main()) 