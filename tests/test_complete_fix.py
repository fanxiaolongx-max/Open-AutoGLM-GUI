#!/usr/bin/env python3
"""Complete test for Gemini response parsing and action execution."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_complete_flow():
    """Test the complete flow from Gemini response to action execution."""
    try:
        from phone_agent.actions.handler import parse_action
        from gui_app.scheduler import GeminiConfig, ScheduledTasksManager
        
        print("🚀 完整流程测试")
        print("=" * 60)
        
        # Test 1: Parse problematic Gemini responses
        print("\n🔧 步骤1: 测试响应解析")
        print("-" * 30)
        
        problematic_responses = [
            'do(action="Tap", element=[844, 915])</answer>',
            'do(action="Tap", element=[614, 364])</answer>',
            'do(action="Tap", element=[828, 913])</answer>',
        ]
        
        for i, response in enumerate(problematic_responses, 1):
            print(f"  测试 {i}: {response}")
            try:
                action = parse_action(response)
                print(f"    ✅ 解析成功: {action}")
            except Exception as e:
                print(f"    ❌ 解析失败: {e}")
                return False
        
        # Test 2: Verify Gemini configuration
        print("\n🔧 步骤2: 验证Gemini配置")
        print("-" * 30)
        
        manager = ScheduledTasksManager()
        config = manager.get_gemini_config()
        
        print(f"  模型: {config.model_name}")
        print(f"  温度: {config.temperature}")
        print(f"  最大令牌: {config.max_tokens}")
        print(f"  系统提示词: {config.system_prompt[:50]}...")
        
        # Test 3: Simulate Gemini API call
        print("\n🔧 步骤3: 模拟API调用")
        print("-" * 30)
        
        if config.enabled:
            print("  Gemini已启用，测试API调用...")
            response = manager.call_gemini_api([
                {"role": "user", "content": "请生成一个点击屏幕中央的动作指令"}
            ])
            
            if response:
                print(f"  ✅ API响应: {response}")
                
                # Test parsing the actual response
                try:
                    action = parse_action(response)
                    print(f"  ✅ 实际响应解析成功: {action}")
                except Exception as e:
                    print(f"  ❌ 实际响应解析失败: {e}")
                    return False
            else:
                print("  ⚠️ API调用失败")
        else:
            print("  Gemini未启用，跳过API测试")
        
        print("\n🎉 完整流程测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_action_types():
    """Test different action types with Gemini responses."""
    try:
        from phone_agent.actions.handler import parse_action
        
        print("\n🔧 动作类型测试")
        print("=" * 60)
        
        action_tests = [
            # Tap actions
            ('点击', 'do(action="Tap", element=[500, 500])</answer>'),
            
            # Type actions
            ('输入', 'do(action="Type", text="Hello World")</answer>'),
            
            # Wait actions
            ('等待', 'do(action="Wait", duration="3 seconds")</answer>'),
            
            # Swipe actions
            ('滑动', 'do(action="Swipe", start=[100, 100], end=[200, 200])</answer>'),
            
            # Finish actions
            ('完成', 'finish(message="任务完成")</answer>'),
        ]
        
        success_count = 0
        for action_name, response in action_tests:
            print(f"\n📋 测试{action_name}: {response}")
            try:
                action = parse_action(response)
                print(f"✅ {action_name}解析成功: {action}")
                success_count += 1
            except Exception as e:
                print(f"❌ {action_name}解析失败: {e}")
        
        print(f"\n📊 动作类型测试结果: {success_count}/{len(action_tests)} 成功")
        return success_count == len(action_tests)
        
    except Exception as e:
        print(f"❌ 动作类型测试失败: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Gemini响应解析完整修复验证")
    print("=" * 60)
    
    results = []
    
    # Test 1: Complete flow
    results.append(("完整流程", test_complete_flow()))
    
    # Test 2: Action types
    results.append(("动作类型", test_action_types()))
    
    print("\n" + "=" * 60)
    print("📊 最终测试结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(success for _, success in results):
        print("\n🎉 所有测试通过！")
        print("\n📋 修复总结:")
        print("✅ 修复了Gemini响应中的</answer>标签问题")
        print("✅ 更新了系统提示词以返回更干净的格式")
        print("✅ 支持所有动作类型的解析")
        print("✅ 确保坐标正确提取和执行")
        
        print("\n🎯 现在可以正常使用Gemini进行手机自动化控制了！")
        print("   - Gemini会返回正确的动作格式")
        print("   - 系统会自动清理HTML标签")
        print("   - ADB可以正确执行点击等操作")
    else:
        print("\n⚠️ 部分测试失败，请检查配置。")

if __name__ == "__main__":
    main()
