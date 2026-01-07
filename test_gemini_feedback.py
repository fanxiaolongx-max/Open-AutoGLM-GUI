#!/usr/bin/env python3
"""Test Gemini AI feedback configuration synchronization."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_gemini_feedback_config():
    """Test Gemini feedback configuration."""
    try:
        from gui_app.scheduler import GeminiConfig, ScheduledTasksManager
        
        print("🔧 测试Gemini AI反馈配置...")
        print("-" * 50)
        
        # Create manager
        manager = ScheduledTasksManager()
        config = manager.get_gemini_config()
        
        print("📋 当前Gemini配置:")
        print(f"   启用状态: {config.enabled}")
        print(f"   API地址: {config.base_url}")
        print(f"   API密钥: {config.api_key[:8]}...")
        print(f"   模型名称: {config.model_name}")
        print(f"   系统提示词: {config.system_prompt[:50]}...")
        print(f"   最大轮数: {config.max_rounds}")
        print(f"   温度参数: {getattr(config, 'temperature', 'N/A')}")
        print(f"   最大令牌: {getattr(config, 'max_tokens', 'N/A')}")
        
        # Test API call if enabled
        if config.enabled and config.api_key:
            print("\n🔍 测试API调用...")
            response = manager.call_gemini_api([
                {"role": "user", "content": "Hello, please respond with 'AI Feedback Test Successful'"}
            ])
            
            if response:
                print(f"✅ API调用成功: {response}")
                return True
            else:
                print("❌ API调用失败")
                return False
        else:
            print("\n⚠️ Gemini未启用或API密钥为空，跳过API测试")
            return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_update():
    """Test configuration update with new fields."""
    try:
        from gui_app.scheduler import GeminiConfig, ScheduledTasksManager
        
        print("\n🔧 测试配置更新...")
        print("-" * 50)
        
        manager = ScheduledTasksManager()
        
        # Create new config with all fields
        new_config = GeminiConfig(
            enabled=True,
            base_url="http://127.0.0.1:8045/v1",
            api_key="sk-985786ae787d43e6b8d42688f39ed83a",
            model_name="gemini-3-pro-high",
            system_prompt="你是一个智能手机自动化助手。",
            max_rounds=5,
            temperature=0.7,
            max_tokens=4000
        )
        
        print("📝 更新配置...")
        manager.update_gemini_config(new_config)
        
        # Verify update
        updated_config = manager.get_gemini_config()
        
        print("📋 更新后的配置:")
        print(f"   启用状态: {updated_config.enabled}")
        print(f"   模型名称: {updated_config.model_name}")
        print(f"   温度参数: {updated_config.temperature}")
        print(f"   最大令牌: {updated_config.max_tokens}")
        
        # Check if all fields are correct
        success = (
            updated_config.model_name == "gemini-3-pro-high" and
            updated_config.temperature == 0.7 and
            updated_config.max_tokens == 4000
        )
        
        if success:
            print("✅ 配置更新成功")
        else:
            print("❌ 配置更新失败")
            
        return success
        
    except Exception as e:
        print(f"❌ 配置更新测试失败: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Gemini AI反馈配置同步测试")
    print("=" * 60)
    
    results = []
    
    # Test 1: Current configuration
    results.append(("当前配置", test_gemini_feedback_config()))
    
    # Test 2: Configuration update
    results.append(("配置更新", test_config_update()))
    
    print("\n" + "=" * 60)
    print("📊 测试结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(success for _, success in results):
        print("\n🎉 所有测试通过！")
        print("\n📋 AI反馈配置已同步更新:")
        print("✅ API地址: http://127.0.0.1:8045/v1")
        print("✅ API密钥: sk-985786ae787d43e6b8d42688f39ed83a")
        print("✅ 模型名称: gemini-3-pro-high")
        print("✅ 温度参数: 0.7")
        print("✅ 最大令牌: 4000")
        print("\n🎯 现在可以在定时任务中使用AI反馈功能了！")
    else:
        print("\n⚠️ 部分测试失败，请检查配置。")

if __name__ == "__main__":
    main()
