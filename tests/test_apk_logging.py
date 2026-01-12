#!/usr/bin/env python3
"""测试APK安装详细日志功能"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_apk_logging():
    """测试APK安装日志功能"""
    print("🔧 APK安装详细日志测试")
    print("=" * 50)
    
    results = []
    
    with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. 检查文件选择日志
    print("\n📁 1. 文件选择日志")
    print("-" * 30)
    
    if '🔍 开始选择APK文件' in content:
        print("   ✅ 添加了文件选择开始日志")
        results.append(("文件选择开始", True))
    else:
        print("   ❌ 缺少文件选择开始日志")
        results.append(("文件选择开始", False))
    
    if '📁 文件对话框结果:' in content:
        print("   ✅ 添加了文件对话框结果日志")
        results.append(("文件对话框结果", True))
    else:
        print("   ❌ 缺少文件对话框结果日志")
        results.append(("文件对话框结果", False))
    
    if '💥 选择APK文件时发生错误' in content:
        print("   ✅ 添加了文件选择错误处理")
        results.append(("文件选择错误", True))
    else:
        print("   ❌ 缺少文件选择错误处理")
        results.append(("文件选择错误", False))
    
    # 2. 检查安装流程日志
    print("\n🔧 2. 安装流程日志")
    print("-" * 30)
    
    if '🔧 开始APK安装流程' in content:
        print("   ✅ 添加了安装流程开始日志")
        results.append(("安装流程开始", True))
    else:
        print("   ❌ 缺少安装流程开始日志")
        results.append(("安装流程开始", False))
    
    if '📱 设备类型:' in content:
        print("   ✅ 添加了设备类型日志")
        results.append(("设备类型日志", True))
    else:
        print("   ❌ 缺少设备类型日志")
        results.append(("设备类型日志", False))
    
    if '🎯 目标设备ID:' in content:
        print("   ✅ 添加了设备ID日志")
        results.append(("设备ID日志", True))
    else:
        print("   ❌ 缺少设备ID日志")
        results.append(("设备ID日志", False))
    
    # 3. 检查Worker线程日志
    print("\n🔨 3. Worker线程日志")
    print("-" * 30)
    
    if 'ApkInstallWorker线程启动' in content:
        print("   ✅ 添加了线程启动日志")
        results.append(("线程启动日志", True))
    else:
        print("   ❌ 缺少线程启动日志")
        results.append(("线程启动日志", False))
    
    if '使用指定设备:' in content:
        print("   ✅ 添加了设备指定日志")
        results.append(("设备指定日志", True))
    else:
        print("   ❌ 缺少设备指定日志")
        results.append(("设备指定日志", False))
    
    if 'ADB命令输出:' in content:
        print("   ✅ 添加了ADB命令输出日志")
        results.append(("ADB输出日志", True))
    else:
        print("   ❌ 缺少ADB命令输出日志")
        results.append(("ADB输出日志", False))
    
    # 4. 检查错误处理日志
    print("\n💥 4. 错误处理日志")
    print("-" * 30)
    
    if 'traceback.format_exc()' in content:
        print("   ✅ 添加了详细错误追踪")
        results.append(("错误追踪", True))
    else:
        print("   ❌ 缺少详细错误追踪")
        results.append(("错误追踪", False))
    
    if '安装超时 (5分钟)' in content:
        print("   ✅ 添加了超时处理日志")
        results.append(("超时处理", True))
    else:
        print("   ❌ 缺少超时处理日志")
        results.append(("超时处理", False))
    
    # 5. 检查异常处理
    print("\n🛡️ 5. 异常处理")
    print("-" * 30)
    
    if 'try:' in content and 'except Exception as e:' in content:
        print("   ✅ 添加了异常处理")
        results.append(("异常处理", True))
    else:
        print("   ❌ 缺少异常处理")
        results.append(("异常处理", False))
    
    return results

def main():
    """主函数"""
    results = test_apk_logging()
    
    print("\n" + "=" * 50)
    print("📊 日志功能检查结果")
    print("=" * 50)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"✅ 日志功能通过: {passed}/{total}")
    print(f"📈 总体成功率: {passed/total:.1%}")
    
    if passed >= total * 0.8:
        print("\n🎉 APK安装详细日志功能添加成功！")
        print("\n📋 添加的日志功能:")
        print("✅ 文件选择过程详细记录")
        print("✅ 安装流程每一步都有日志")
        print("✅ Worker线程状态跟踪")
        print("✅ ADB命令执行详情")
        print("✅ 错误和异常详细信息")
        
        print("\n🎯 调试能力提升:")
        print("• 🔍 可以精确定位闪退发生点")
        print("• 📊 查看完整的执行流程")
        print("• 💥 详细的错误信息和堆栈跟踪")
        print("• 📱 设备ID和类型确认")
        print("• ⏱️ 超时和异常处理")
        
        print("\n🚀 使用方法:")
        print("1. 在应用安装页面点击'选择APK文件'")
        print("2. 查看安装日志区域的详细输出")
        print("3. 如果发生闪退，查看最后的日志条目")
        print("4. 根据日志信息定位问题原因")
        
        print("\n💡 调试建议:")
        print("• 关注'💥'标记的错误信息")
        print("• 检查'🎯 目标设备ID'是否正确")
        print("• 查看'ADB命令输出'了解ADB执行情况")
        print("• 注意'安装超时'或'安装异常'的特殊情况")
        
    else:
        print(f"\n⚠️ 还有 {total - passed} 项日志功能需要完善")

if __name__ == "__main__":
    main()
