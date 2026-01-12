#!/usr/bin/env python3
"""Detailed Gemini API connection test and diagnostics."""

import sys
import os
import time

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_openai_connection():
    """Test OpenAI compatible connection with detailed diagnostics."""
    try:
        from openai import OpenAI
        
        print("🔧 测试OpenAI兼容连接...")
        print("-" * 50)
        
        # Test with different configurations
        configs = [
            {
                "name": "标准配置",
                "base_url": "http://127.0.0.1:8045/v1",
                "api_key": "sk-985786ae787d43e6b8d42688f39ed83a",
                "timeout": 30
            },
            {
                "name": "长超时配置", 
                "base_url": "http://127.0.0.1:8045/v1",
                "api_key": "sk-985786ae787d43e6b8d42688f39ed83a",
                "timeout": 60
            }
        ]
        
        for config in configs:
            print(f"\n📋 测试配置: {config['name']}")
            print(f"   地址: {config['base_url']}")
            print(f"   超时: {config['timeout']}秒")
            
            try:
                client = OpenAI(
                    base_url=config['base_url'],
                    api_key=config['api_key'],
                    timeout=config['timeout']
                )
                
                # Test 1: Models list
                print("   🔍 测试1: 获取模型列表...")
                try:
                    start_time = time.time()
                    models = client.models.list()
                    elapsed = time.time() - start_time
                    print(f"   ✅ 模型列表获取成功 ({elapsed:.2f}秒)")
                    print(f"   📊 发现模型数量: {len(models.data)}")
                    for model in models.data[:3]:  # Show first 3 models
                        print(f"      - {model.id}")
                except Exception as e:
                    print(f"   ❌ 模型列表获取失败: {e}")
                
                # Test 2: Chat completion
                print("   🔍 测试2: 聊天补全...")
                try:
                    start_time = time.time()
                    response = client.chat.completions.create(
                        model="gemini-3-pro-high",
                        messages=[{"role": "user", "content": "Hello"}],
                        max_tokens=10,
                        temperature=0.1
                    )
                    elapsed = time.time() - start_time
                    print(f"   ✅ 聊天补全成功 ({elapsed:.2f}秒)")
                    if response.choices and len(response.choices) > 0:
                        content = response.choices[0].message.content
                        print(f"   📝 响应内容: {content}")
                    else:
                        print("   ⚠️ 响应为空")
                except Exception as e:
                    print(f"   ❌ 聊天补全失败: {e}")
                
                # Test 3: Simple ping
                print("   🔍 测试3: 简单连接测试...")
                try:
                    import requests
                    start_time = time.time()
                    response = requests.get(f"{config['base_url']}/models", timeout=10)
                    elapsed = time.time() - start_time
                    print(f"   ✅ HTTP连接测试成功 ({elapsed:.2f}秒)")
                    print(f"   📊 状态码: {response.status_code}")
                    if response.status_code == 200:
                        data = response.json()
                        if 'data' in data:
                            print(f"   📊 模型数量: {len(data['data'])}")
                except Exception as e:
                    print(f"   ❌ HTTP连接测试失败: {e}")
                
            except Exception as e:
                print(f"   ❌ 客户端创建失败: {e}")
        
        return True
        
    except ImportError:
        print("❌ OpenAI库未安装")
        return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False

def test_model_service_manager():
    """Test the ModelServicesManager test_service method."""
    try:
        from gui_app.model_services import ModelServicesManager, ModelServiceConfig
        
        print("\n🔧 测试模型服务管理器...")
        print("-" * 50)
        
        manager = ModelServicesManager()
        
        # Get Gemini service
        gemini_service = None
        for service in manager.get_all_services():
            if service.id == "gemini_antigravity":
                gemini_service = service
                break
        
        if not gemini_service:
            # Try to find it in presets
            for preset in manager.get_preset_templates():
                if preset.id == "gemini_antigravity":
                    gemini_service = preset
                    break
        
        if not gemini_service:
            print("❌ 未找到Gemini服务配置")
            return False
        
        print(f"📋 服务信息:")
        print(f"   名称: {gemini_service.name}")
        print(f"   地址: {gemini_service.base_url}")
        print(f"   模型: {gemini_service.model_name}")
        print(f"   密钥: {gemini_service.api_key[:8]}...")
        
        # Test the service
        print("\n🔍 调用test_service方法...")
        success, message = manager.test_service(gemini_service)
        print(f"📊 测试结果: {'成功' if success else '失败'}")
        print(f"📝 返回消息: {message}")
        
        return success
        
    except Exception as e:
        print(f"❌ 模型服务管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_direct_gemini():
    """Test direct Gemini API call."""
    try:
        import google.generativeai as genai
        
        print("\n🔧 测试直接Gemini API...")
        print("-" * 50)
        
        genai.configure(
            api_key="sk-985786ae787d43e6b8d42688f39ed83a",
            transport='rest',
            client_options={'api_endpoint': 'http://127.0.0.1:8045'}
        )
        
        model = genai.GenerativeModel('gemini-3-pro-high')
        
        print("🔍 发送测试请求...")
        start_time = time.time()
        response = model.generate_content("Hello, respond with just 'OK'")
        elapsed = time.time() - start_time
        
        print(f"✅ 直接API调用成功 ({elapsed:.2f}秒)")
        print(f"📝 响应: {response.text}")
        
        return True
        
    except Exception as e:
        print(f"❌ 直接API调用失败: {e}")
        return False

def main():
    """Run all diagnostic tests."""
    print("🚀 Gemini API 连接诊断")
    print("=" * 60)
    
    results = []
    
    # Test 1: Direct Gemini API
    results.append(("直接Gemini API", test_direct_gemini()))
    
    # Test 2: OpenAI compatible connection
    results.append(("OpenAI兼容接口", test_openai_connection()))
    
    # Test 3: Model service manager
    results.append(("模型服务管理器", test_model_service_manager()))
    
    print("\n" + "=" * 60)
    print("📊 诊断结果总结:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(success for _, success in results):
        print("\n🎉 所有测试通过！连接应该正常。")
        print("如果GUI中仍然显示失败，可能是界面更新问题。")
    else:
        print("\n⚠️ 部分测试失败，需要进一步排查。")
        print("建议检查:")
        print("1. 网络连接是否正常")
        print("2. Antigravity代理服务是否运行")
        print("3. API密钥是否正确")
        print("4. 防火墙设置是否阻止连接")

if __name__ == "__main__":
    main()
