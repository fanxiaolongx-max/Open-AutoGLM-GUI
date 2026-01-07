#!/usr/bin/env python3
"""Test Gemini API configuration with Antigravity proxy."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_gemini_direct():
    """Test direct Gemini API call using the provided script."""
    try:
        import google.generativeai as genai
        
        print("🔧 测试直接Gemini API调用...")
        
        # 使用 Antigravity 代理地址 (推荐 127.0.0.1)
        genai.configure(
            api_key="sk-985786ae787d43e6b8d42688f39ed83a",
            transport='rest',
            client_options={'api_endpoint': 'http://127.0.0.1:8045'}
        )
        
        model = genai.GenerativeModel('gemini-3-pro-high')
        response = model.generate_content("Hello, please respond in Chinese: 你好，请简单介绍一下你自己")
        print(f"✅ Gemini API 响应: {response.text}")
        return True
        
    except ImportError:
        print("❌ 需要安装 google-generativeai: pip install google-generativeai")
        return False
    except Exception as e:
        print(f"❌ Gemini API 调用失败: {e}")
        return False

def test_gemini_openai_compat():
    """Test Gemini API through OpenAI compatible interface."""
    try:
        from openai import OpenAI
        
        print("\n🔧 测试OpenAI兼容接口调用Gemini...")
        
        client = OpenAI(
            base_url="http://127.0.0.1:8045/v1",
            api_key="sk-985786ae787d43e6b8d42688f39ed83a"
        )
        
        response = client.chat.completions.create(
            model="gemini-3-pro-high",
            messages=[
                {"role": "user", "content": "Hello, please respond in Chinese: 你好，请简单介绍一下你自己"}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        if response and response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content
            print(f"✅ OpenAI兼容接口响应: {content}")
            return True
        else:
            print("❌ OpenAI兼容接口响应为空")
            return False
        
    except ImportError:
        print("❌ 需要安装 openai: pip install openai")
        return False
    except Exception as e:
        print(f"❌ OpenAI兼容接口调用失败: {e}")
        return False

def test_model_service_config():
    """Test the model service configuration."""
    try:
        from gui_app.model_services import ModelServicesManager, ModelServiceConfig
        
        print("\n🔧 测试模型服务配置...")
        
        manager = ModelServicesManager()
        
        # Check if Gemini preset is available
        gemini_service = None
        for service in manager.get_preset_templates():
            if service.id == "gemini_antigravity":
                gemini_service = service
                break
        
        if gemini_service:
            print(f"✅ 找到Gemini预置配置:")
            print(f"   名称: {gemini_service.name}")
            print(f"   地址: {gemini_service.base_url}")
            print(f"   模型: {gemini_service.model_name}")
            print(f"   API密钥: {gemini_service.api_key[:8]}...")
            
            # Test the service
            success, message = manager.test_service(gemini_service)
            if success:
                print(f"✅ 服务测试成功: {message}")
                return True
            else:
                print(f"❌ 服务测试失败: {message}")
                return False
        else:
            print("❌ 未找到Gemini预置配置")
            return False
            
    except Exception as e:
        print(f"❌ 模型服务配置测试失败: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 开始测试Gemini API配置...")
    print("=" * 60)
    
    results = []
    
    # Test 1: Direct Gemini API
    results.append(test_gemini_direct())
    
    # Test 2: OpenAI compatible interface
    results.append(test_gemini_openai_compat())
    
    # Test 3: Model service configuration
    results.append(test_model_service_config())
    
    print("\n" + "=" * 60)
    print("📊 测试结果总结:")
    print(f"   直接API调用: {'✅ 通过' if results[0] else '❌ 失败'}")
    print(f"   OpenAI兼容接口: {'✅ 通过' if results[1] else '❌ 失败'}")
    print(f"   模型服务配置: {'✅ 通过' if results[2] else '❌ 失败'}")
    
    if all(results):
        print("\n🎉 所有测试通过！Gemini API配置正常。")
        return 0
    else:
        print("\n⚠️ 部分测试失败，请检查配置。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
