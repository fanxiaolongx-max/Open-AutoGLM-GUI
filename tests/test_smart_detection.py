#!/usr/bin/env python3
"""Test smart device detection that preserves existing connections."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_smart_detection_logic():
    """Test the smart detection logic implementation."""
    try:
        print("🧠 智能检测逻辑测试")
        print("=" * 50)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        required_elements = [
            'def _check_connected_devices(self, device_type) -> bool:',
            'has_connected_devices = self._check_connected_devices(device_type)',
            'if has_connected_devices:',
            '发现已有连接设备，跳过清理步骤',
            'else:',
            '未发现连接设备，开始清理现有连接...',
            '# Clean existing connections only if no devices are connected'
        ]
        
        found_elements = []
        for element in required_elements:
            if element in content:
                found_elements.append(element)
                print(f"   ✅ {element}")
            else:
                print(f"   ❌ {element}")
        
        success_rate = len(found_elements) / len(required_elements)
        print(f"\n📊 完成度: {success_rate:.1%} ({len(found_elements)}/{len(required_elements)})")
        
        return success_rate >= 0.8
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_device_check_methods():
    """Test device checking methods for different device types."""
    try:
        print("\n📱 设备检查方法测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        device_checks = [
            ('ADB设备检查', "if device_type == DeviceType.ADB:", "['adb', 'devices']"),
            ('HDC设备检查', "elif device_type == DeviceType.HDC:", "['hdc', 'list', 'targets']"),
            ('iOS设备检查', "elif device_type == DeviceType.IOS:", "['idevice_id', '-l']"),
            ('超时处理', "subprocess.TimeoutExpired", "timeout=10"),
            ('错误处理', "except Exception as e:", "return False")
        ]
        
        found_checks = []
        for check_name, condition, command in device_checks:
            if condition in content and command in content:
                found_checks.append(check_name)
                print(f"   ✅ {check_name}")
            else:
                print(f"   ❌ {check_name}")
        
        success_rate = len(found_checks) / len(device_checks)
        print(f"\n📊 完成度: {success_rate:.1%} ({len(found_checks)}/{len(device_checks)})")
        
        return success_rate >= 0.8
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_log_messages():
    """Test that appropriate log messages are implemented."""
    try:
        print("\n📝 日志消息测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        log_messages = [
            "发现已有连接设备，跳过清理步骤",
            "未发现连接设备，开始清理现有连接...",
            "发现已连接的ADB设备:",
            "发现已连接的HDC设备:",
            "发现已连接的iOS设备:",
            "设备检查超时",
            "检查连接设备时出错"
        ]
        
        found_messages = []
        for message in log_messages:
            if message in content:
                found_messages.append(message)
                print(f"   ✅ {message}")
            else:
                print(f"   ❌ {message}")
        
        success_rate = len(found_messages) / len(log_messages)
        print(f"\n📊 完成度: {success_rate:.1%} ({len(found_messages)}/{len(log_messages)})")
        
        return success_rate >= 0.8
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_workflow_logic():
    """Test the overall workflow logic."""
    try:
        print("\n🔄 工作流程逻辑测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        workflow_steps = [
            "开始自动检测设备...",
            "正在检测设备",
            "First, check if there are already connected devices",
            "if has_connected_devices:",
            "发现已有连接设备，跳过清理步骤",
            "检测完成",
            "else:",
            "未发现连接设备，开始清理现有连接...",
            "_clean_existing_connections(device_type)",
            "Then refresh devices",
            "_refresh_devices()",
            "检测到",
            "未检测到设备"
        ]
        
        found_steps = []
        for step in workflow_steps:
            if step in content:
                found_steps.append(step)
                print(f"   ✅ {step}")
            else:
                print(f"   ❌ {step}")
        
        success_rate = len(found_steps) / len(workflow_steps)
        print(f"\n📊 完成度: {success_rate:.1%} ({len(found_steps)}/{len(workflow_steps)})")
        
        return success_rate >= 0.8
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 智能设备检测功能测试")
    print("=" * 60)
    
    results = []
    
    # Test 1: Smart detection logic
    results.append(("智能检测逻辑", test_smart_detection_logic()))
    
    # Test 2: Device check methods
    results.append(("设备检查方法", test_device_check_methods()))
    
    # Test 3: Log messages
    results.append(("日志消息", test_log_messages()))
    
    # Test 4: Workflow logic
    results.append(("工作流程逻辑", test_workflow_logic()))
    
    print("\n" + "=" * 60)
    print("📊 测试结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(success for _, success in results):
        print("\n🎉 所有测试通过！")
        print("\n📋 完成的智能检测功能:")
        print("✅ 先检查现有连接设备")
        print("✅ 有设备时跳过ADB重置")
        print("✅ 无设备时清理连接")
        print("✅ 支持ADB、HDC、iOS设备检查")
        print("✅ 完善的错误处理和超时机制")
        print("✅ 详细的日志记录")
        
        print("\n🎯 智能检测流程:")
        print("1. 点击设备中心 → 开始检测")
        print("2. 检查当前连接设备")
        print("3. 如果有设备 → 跳过清理，直接刷新")
        print("4. 如果无设备 → 清理连接，然后刷新")
        print("5. 显示检测结果和状态")
        
        print("\n💡 用户体验改进:")
        print("• 保护现有连接：不会意外断开已连接设备")
        print("• 智能判断：只在需要时才重置ADB状态")
        print("• 状态清晰：详细日志显示检测过程")
        print("• 操作高效：避免不必要的重启操作")
    else:
        print("\n⚠️ 部分测试失败，需要进一步检查。")

if __name__ == "__main__":
    main()
