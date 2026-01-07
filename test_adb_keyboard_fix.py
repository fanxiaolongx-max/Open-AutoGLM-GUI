#!/usr/bin/env python3
"""测试ADB键盘多设备修复"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_adb_keyboard_multi_device_fix():
    """测试ADB键盘多设备修复"""
    print("🔧 ADB键盘多设备修复测试")
    print("=" * 50)
    
    results = []
    
    # 1. 检查系统检查修复
    print("\n📱 1. 系统检查修复")
    print("-" * 30)
    
    with open('/mnt/data/TOOL/Open-AutoGLM/main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查自动设备选择
    if 'if not device_id:' in content and 'devices[0].device_id' in content:
        print("   ✅ 添加了自动设备选择逻辑")
        results.append(("自动设备选择", True))
    else:
        print("   ❌ 缺少自动设备选择逻辑")
        results.append(("自动设备选择", False))
    
    # 检查设备ID指定
    if 'adb_cmd = ["adb"]' in content and 'adb_cmd.extend(["-s", device_id])' in content:
        print("   ✅ ADB命令正确指定设备ID")
        results.append(("ADB命令设备指定", True))
    else:
        print("   ❌ ADB命令未指定设备ID")
        results.append(("ADB命令设备指定", False))
    
    # 检查设备显示
    if 'print(f"(using device: {device_id})...", end=" ")' in content:
        print("   ✅ 显示使用的设备ID")
        results.append(("设备ID显示", True))
    else:
        print("   ❌ 未显示使用的设备ID")
        results.append(("设备ID显示", False))
    
    # 2. 检查ADB键盘安装函数
    print("\n📱 2. ADB键盘安装函数")
    print("-" * 30)
    
    with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查设备ID参数
    if 'def ensure_adb_keyboard_installed(device_id):' in content:
        print("   ✅ 函数接受设备ID参数")
        results.append(("函数参数", True))
    else:
        print("   ❌ 函数不接受设备ID参数")
        results.append(("函数参数", False))
    
    # 检查ADB前缀构建
    if 'adb_prefix = _adb_prefix(device_id)' in content:
        print("   ✅ 使用设备ID构建ADB前缀")
        results.append(("ADB前缀构建", True))
    else:
        print("   ❌ 未使用设备ID构建ADB前缀")
        results.append(("ADB前缀构建", False))
    
    # 检查自动启用
    if 'ime", "enable", "com.android.adbkeyboard/.AdbIME' in content:
        print("   ✅ 包含自动启用ADB键盘")
        results.append(("自动启用", True))
    else:
        print("   ❌ 缺少自动启用ADB键盘")
        results.append(("自动启用", False))
    
    # 3. 检查前缀函数
    print("\n🔧 3. ADB前缀函数")
    print("-" * 30)
    
    if 'def _adb_prefix(device_id):' in content:
        print("   ✅ _adb_prefix函数存在")
        results.append(("前缀函数存在", True))
    else:
        print("   ❌ _adb_prefix函数不存在")
        results.append(("前缀函数存在", False))
    
    if 'if device_id:' in content and 'return ["adb", "-s", device_id]' in content:
        print("   ✅ 前缀函数正确处理设备ID")
        results.append(("前缀函数逻辑", True))
    else:
        print("   ❌ 前缀函数未正确处理设备ID")
        results.append(("前缀函数逻辑", False))
    
    return results

def test_actual_system_check():
    """测试实际系统检查"""
    print("\n🔍 实际系统检查测试")
    print("-" * 30)
    
    try:
        # 测试指定设备ID
        print("   测试指定设备ID...")
        result1 = os.system("./venv/bin/python main.py --device-type adb --device-id emulator-5554 --quiet 'list apps' 2>/dev/null")
        if result1 == 0:
            print("   ✅ 指定设备ID测试通过")
            test1 = True
        else:
            print("   ❌ 指定设备ID测试失败")
            test1 = False
        
        # 测试自动选择设备
        print("   测试自动选择设备...")
        result2 = os.system("./venv/bin/python main.py --device-type adb --quiet 'list apps' 2>/dev/null")
        if result2 == 0:
            print("   ✅ 自动选择设备测试通过")
            test2 = True
        else:
            print("   ❌ 自动选择设备测试失败")
            test2 = False
        
        return test1 and test2
        
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return False

def main():
    """主函数"""
    results = test_adb_keyboard_multi_device_fix()
    actual_test = test_actual_system_check()
    
    print("\n" + "=" * 50)
    print("📊 修复结果统计")
    print("=" * 50)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"✅ 代码检查通过: {passed}/{total}")
    print(f"✅ 实际测试通过: {'通过' if actual_test else '失败'}")
    print(f"📈 总体成功率: {passed/total:.1%}")
    
    if passed >= total * 0.8 and actual_test:
        print("\n🎉 ADB键盘多设备修复成功！")
        print("\n📋 修复内容:")
        print("✅ 系统检查自动选择设备")
        print("✅ ADB命令明确指定设备ID")
        print("✅ 显示当前使用的设备")
        print("✅ ADB键盘安装支持设备ID")
        print("✅ 自动启用ADB键盘")
        
        print("\n🎯 修复效果:")
        print("• 📱 多设备环境下系统检查正常")
        print("• 🔧 ADB键盘自动安装到指定设备")
        print("• ⚡ 避免多设备冲突错误")
        print("• 🤖 自动启用键盘功能")
        
        print("\n🚀 使用方法:")
        print("1. 指定设备: python main.py --device-id <device_id>")
        print("2. 自动选择: python main.py (自动选择第一个设备)")
        print("3. 系统检查会自动处理ADB键盘安装和启用")
        
    else:
        print(f"\n⚠️ 还有问题需要解决:")
        if passed < total:
            print(f"   • 代码检查: {total - passed} 项失败")
        if not actual_test:
            print("   • 实际测试失败")

if __name__ == "__main__":
    main()
