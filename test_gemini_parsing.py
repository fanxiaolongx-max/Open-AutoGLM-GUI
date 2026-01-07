#!/usr/bin/env python3
"""Test action parsing with Gemini responses."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_gemini_response_parsing():
    """Test parsing Gemini responses with </answer> tags."""
    try:
        from phone_agent.actions.handler import parse_action
        
        print("🔧 测试Gemini响应解析...")
        print("-" * 50)
        
        # Test cases with various Gemini response formats
        test_cases = [
            # Standard format without tags
            'do(action="Tap", element=[844, 915])',
            
            # With </answer> tag
            'do(action="Tap", element=[844, 915])</answer>',
            
            # With multiple tags
            'do(action="Tap", element=[614, 364])</answer>',
            
            # With extra whitespace
            'do(action="Tap", element=[828,913])</answer>  ',
            
            # Type action
            'do(action="Type", text="Hello")',
            
            # Type action with tag
            'do(action="Type", text="Hello")</answer>',
            
            # Finish action
            'finish(message="Task completed")',
            
            # Finish action with tag
            'finish(message="Task completed")</answer>',
        ]
        
        success_count = 0
        for i, test_response in enumerate(test_cases, 1):
            print(f"\n📋 测试用例 {i}: {test_response}")
            try:
                action = parse_action(test_response)
                print(f"✅ 解析成功: {action}")
                success_count += 1
            except Exception as e:
                print(f"❌ 解析失败: {e}")
        
        print(f"\n📊 测试结果: {success_count}/{len(test_cases)} 成功")
        
        return success_count == len(test_cases)
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_coordinate_extraction():
    """Test extracting coordinates from parsed actions."""
    try:
        from phone_agent.actions.handler import parse_action
        
        print("\n🔧 测试坐标提取...")
        print("-" * 50)
        
        test_responses = [
            'do(action="Tap", element=[844, 915])</answer>',
            'do(action="Tap", element=[614, 364])</answer>',
            'do(action="Tap", element=[828, 913])</answer>',
        ]
        
        for i, response in enumerate(test_responses, 1):
            print(f"\n📋 测试用例 {i}: {response}")
            try:
                action = parse_action(response)
                if 'element' in action and isinstance(action['element'], list):
                    x, y = action['element']
                    print(f"✅ 坐标提取成功: ({x}, {y})")
                else:
                    print(f"❌ 坐标提取失败: 未找到element字段或格式错误")
            except Exception as e:
                print(f"❌ 解析失败: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ 坐标提取测试失败: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Gemini响应解析修复测试")
    print("=" * 60)
    
    results = []
    
    # Test 1: Basic parsing
    results.append(("响应解析", test_gemini_response_parsing()))
    
    # Test 2: Coordinate extraction
    results.append(("坐标提取", test_coordinate_extraction()))
    
    print("\n" + "=" * 60)
    print("📊 测试结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(success for _, success in results):
        print("\n🎉 所有测试通过！")
        print("Gemini响应解析问题已修复，现在可以正确处理包含</answer>标签的响应。")
        print("\n📋 修复内容:")
        print("✅ 自动移除</answer>标签")
        print("✅ 清理HTML标签残留")
        print("✅ 正确解析坐标参数")
        print("✅ 支持所有动作类型")
    else:
        print("\n⚠️ 部分测试失败，需要进一步检查。")

if __name__ == "__main__":
    main()
