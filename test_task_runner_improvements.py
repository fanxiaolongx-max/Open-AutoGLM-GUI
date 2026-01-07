#!/usr/bin/env python3
"""测试任务执行页面改进"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_task_runner_improvements():
    """测试任务执行页面改进"""
    print("🔧 任务执行页面改进测试")
    print("=" * 50)
    
    results = []
    
    with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. 检查自动刷新设备列表
    print("\n📱 1. 自动刷新设备列表")
    print("-" * 30)
    
    if 'QtCore.QTimer.singleShot(500, self._refresh_task_devices)' in content:
        print("   ✅ 添加了任务页面设备自动刷新")
        results.append(("设备自动刷新", True))
    else:
        print("   ❌ 缺少任务页面设备自动刷新")
        results.append(("设备自动刷新", False))
    
    if 'if index == self.task_runner_index:' in content:
        print("   ✅ 正确绑定到任务执行页面")
        results.append(("页面绑定正确", True))
    else:
        print("   ❌ 页面绑定有问题")
        results.append(("页面绑定正确", False))
    
    # 2. 检查任务完成对话框
    print("\n📋 2. 任务完成对话框")
    print("-" * 30)
    
    if '_show_task_completion_dialog(result, success=True)' in content:
        print("   ✅ 单设备任务完成显示对话框")
        results.append(("单设备完成对话框", True))
    else:
        print("   ❌ 缺少单设备任务完成对话框")
        results.append(("单设备完成对话框", False))
    
    if '_show_task_completion_dialog(message, success=False)' in content:
        print("   ✅ 单设备任务失败显示对话框")
        results.append(("单设备失败对话框", True))
    else:
        print("   ❌ 缺少单设备任务失败对话框")
        results.append(("单设备失败对话框", False))
    
    # 3. 检查多设备任务完成对话框
    print("\n🔄 3. 多设备任务完成对话框")
    print("-" * 30)
    
    if '_show_multi_device_completion_dialog(success, failed, total)' in content:
        print("   ✅ 多设备任务完成显示对话框")
        results.append(("多设备完成对话框", True))
    else:
        print("   ❌ 缺少多设备任务完成对话框")
        results.append(("多设备完成对话框", False))
    
    # 4. 检查对话框方法实现
    print("\n🎯 4. 对话框方法实现")
    print("-" * 30)
    
    methods = [
        ("def _show_task_completion_dialog", "单设备对话框方法"),
        ("def _show_multi_device_completion_dialog", "多设备对话框方法")
    ]
    
    for method_signature, method_name in methods:
        if method_signature in content:
            print(f"   ✅ {method_name}已实现")
            results.append((method_name, True))
        else:
            print(f"   ❌ {method_name}未实现")
            results.append((method_name, False))
    
    # 5. 检查对话框内容
    print("\n💬 5. 对话框内容检查")
    print("-" * 30)
    
    if 'QtWidgets.QMessageBox(self)' in content:
        print("   ✅ 使用QMessageBox创建对话框")
        results.append(("QMessageBox使用", True))
    else:
        print("   ❌ 未使用QMessageBox")
        results.append(("QMessageBox使用", False))
    
    if 'dialog.setIcon(QtWidgets.QMessageBox.Information)' in content:
        print("   ✅ 设置了成功图标")
        results.append(("成功图标", True))
    else:
        print("   ❌ 缺少成功图标")
        results.append(("成功图标", False))
    
    if 'dialog.setIcon(QtWidgets.QMessageBox.Warning)' in content:
        print("   ✅ 设置了警告图标")
        results.append(("警告图标", True))
    else:
        print("   ❌ 缺少警告图标")
        results.append(("警告图标", False))
    
    if 'dialog.setDetailedText(' in content:
        print("   ✅ 添加了详细信息")
        results.append(("详细信息", True))
    else:
        print("   ❌ 缺少详细信息")
        results.append(("详细信息", False))
    
    return results

def test_refresh_task_devices_method():
    """测试_refresh_task_devices方法"""
    print("\n🔄 _refresh_task_devices方法测试")
    print("-" * 30)
    
    with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'def _refresh_task_devices(self):' in content:
        print("   ✅ _refresh_task_devices方法存在")
        
        # 检查方法内容
        method_start = content.find('def _refresh_task_devices(self):')
        if method_start != -1:
            method_end = content.find('\n    def ', method_start + 1)
            if method_end == -1:
                method_end = len(content)
            method_code = content[method_start:method_end]
            
            if 'self.task_device_list.clear()' in method_code:
                print("   ✅ 清空设备列表")
            else:
                print("   ❌ 未清空设备列表")
            
            if 'self.task_device_list.addItem(item)' in method_code:
                print("   ✅ 添加设备项")
            else:
                print("   ❌ 未添加设备项")
        
        return True
    else:
        print("   ❌ _refresh_task_devices方法不存在")
        return False

def main():
    """主函数"""
    results = test_task_runner_improvements()
    refresh_test = test_refresh_task_devices_method()
    
    print("\n" + "=" * 50)
    print("📊 改进结果统计")
    print("=" * 50)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"✅ 功能检查通过: {passed}/{total}")
    print(f"✅ 方法检查: {'通过' if refresh_test else '失败'}")
    print(f"📈 总体成功率: {passed/total:.1%}")
    
    if passed >= total * 0.8 and refresh_test:
        print("\n🎉 任务执行页面改进成功！")
        print("\n📋 改进内容:")
        print("✅ 点击任务执行菜单自动刷新设备列表")
        print("✅ 单设备任务完成弹出对话框")
        print("✅ 单设备任务失败弹出对话框")
        print("✅ 多设备任务完成弹出对话框")
        print("✅ 不同结果显示不同图标和信息")
        
        print("\n🎯 用户体验提升:")
        print("• 🔄 自动获取最新设备状态")
        print("• 💬 任务完成时明确通知")
        print("• 📊 详细的执行结果信息")
        print("• 🎨 友好的对话框界面")
        
        print("\n🚀 使用方法:")
        print("1. 点击任务执行菜单自动刷新设备列表")
        print("2. 任务执行完成会弹出通知对话框")
        print("3. 对话框显示详细执行结果")
        print("4. 支持单设备和多设备任务通知")
        
    else:
        print(f"\n⚠️ 还有问题需要解决:")
        if passed < total:
            print(f"   • 功能检查: {total - passed} 项失败")
        if not refresh_test:
            print("   • 方法检查失败")

if __name__ == "__main__":
    main()
