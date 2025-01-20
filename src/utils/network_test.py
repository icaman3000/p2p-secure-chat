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

class NetworkTest:
    def __init__(self, network_manager):
        self.network_manager = network_manager
        self.test_results = {}
        
    async def run_tests(self):
        """运行所有网络测试"""
        print("\n=== 开始网络测试 ===")
        
        # 1. 基本网络测试
        await self.test_basic_network()
        
        # 2. STUN 测试
        await self.test_stun()
        
        # 3. 生成测试报告
        self.generate_report()
        
        print("\n=== 网络测试完成 ===")
        return self.test_results
        
    async def test_basic_network(self):
        """测试基本网络功能"""
        print("\n1. 基本网络测试")
        self.test_results["basic"] = {}
        
        # 1.1 检查本地网络
        print("1.1 检查本地网络...")
        if self.network_manager.local_ip:
            print(f"√ 本地 IP: {self.network_manager.local_ip}")
            self.test_results["basic"]["local_ip"] = True
        else:
            print("× 无法获取本地 IP")
            self.test_results["basic"]["local_ip"] = False
            
        # 1.2 检查公网 IP
        print("\n1.2 检查公网 IP...")
        if self.network_manager.public_ip:
            print(f"√ 公网 IP: {self.network_manager.public_ip}")
            self.test_results["basic"]["public_ip"] = True
        else:
            print("× 无法获取公网 IP")
            self.test_results["basic"]["public_ip"] = False
            
    async def test_stun(self):
        """测试 STUN 功能"""
        print("\n2. STUN 测试")
        self.test_results["stun"] = {}
        
        # 2.1 检查 STUN 服务器连接
        print("2.1 检查 STUN 服务器连接...")
        try:
            stun_result = await self.network_manager.network_analyzer.analyze_network()
            if stun_result:
                print("√ STUN 服务器连接成功")
                self.test_results["stun"]["connection"] = True
                
                # 2.2 检查 NAT 类型
                nat_type = stun_result.get("nat_type")
                if nat_type:
                    print(f"√ NAT 类型: {nat_type}")
                    self.test_results["stun"]["nat_type"] = nat_type
                else:
                    print("× 无法确定 NAT 类型")
                    self.test_results["stun"]["nat_type"] = "Unknown"
            else:
                print("× STUN 服务器连接失败")
                self.test_results["stun"]["connection"] = False
        except Exception as e:
            print(f"× STUN 测试失败: {e}")
            self.test_results["stun"]["connection"] = False
            
    def generate_report(self):
        """生成测试报告"""
        print("\n=== 网络测试报告 ===")
        
        # 1. 基本网络状态
        print("\n1. 基本网络状态:")
        basic = self.test_results.get("basic", {})
        print(f"- 本地网络: {'✓' if basic.get('local_ip') else '✗'}")
        print(f"- 公网访问: {'✓' if basic.get('public_ip') else '✗'}")
        
        # 2. STUN 状态
        print("\n2. STUN 状态:")
        stun = self.test_results.get("stun", {})
        print(f"- 服务器连接: {'✓' if stun.get('connection') else '✗'}")
        print(f"- NAT 类型: {stun.get('nat_type', 'Unknown')}")
        
        # 建议
        print("\n建议:")
        if not basic.get('local_ip'):
            print("- 检查网络连接")
        if not basic.get('public_ip'):
            print("- 检查互联网连接")
        if not stun.get('connection'):
            print("- 检查防火墙设置")
            print("- 尝试其他 STUN 服务器")

async def main():
    tester = NetworkTest(NetworkManager())
    await tester.run_tests()

if __name__ == "__main__":
    asyncio.run(main()) 