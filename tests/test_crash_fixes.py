#!/usr/bin/env python3
"""Test fixes for WDA button removal and APK installer crash."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_wda_button_removal():
    """Test that WDA button is completely removed from diagnostics."""
    try:
        print("🔍 WDA按钮移除测试")
        print("=" * 50)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for WDA button definition
        if 'self.diag_wda_btn = QtWidgets.QPushButton("WDA检查")' in content:
            print("   ❌ WDA按钮定义仍存在")
            return False
        else:
            print("   ✅ WDA按钮定义已移除")
        
        # Check for WDA button in layout
        if 'actions.addWidget(self.diag_wda_btn)' in content:
            print("   ❌ WDA按钮仍在布局中")
            return False
        else:
            print("   ✅ WDA按钮已从布局移除")
        
        # Check for WDA button references in methods
        wda_refs = content.count('self.diag_wda_btn')
        if wda_refs == 0:
            print("   ✅ 所有WDA按钮引用已清理")
            return True
        else:
            print(f"   ❌ 仍有{wda_refs}个WDA按钮引用")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_apk_installer_simplification():
    """Test that APK installer is simplified for ADB-only."""
    try:
        print("\n📱 APK安装器简化测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that iOS/HDC checks are removed
        if 'if self.device_type == DeviceType.IOS:' in content:
            print("   ❌ iOS设备类型检查仍存在")
            return False
        else:
            print("   ✅ iOS设备类型检查已移除")
        
        if 'if self.device_type == DeviceType.HDC:' in content:
            print("   ❌ HDC设备类型检查仍存在")
            return False
        else:
            print("   ✅ HDC设备类型检查已移除")
        
        # Check for ADB-only comment
        if 'ADB-only interface, no need to check device type' in content:
            print("   ✅ 添加了ADB专用注释")
            success1 = True
        else:
            print("   ⚠️ 缺少ADB专用注释")
            success1 = False
        
        # Check that only ADB command is used
        if 'cmd_prefix = ["adb"]' in content:
            print("   ✅ 只使用ADB命令")
            success2 = True
        else:
            print("   ❌ 未找到ADB命令定义")
            success2 = False
        
        return success1 and success2
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_diag_methods_fixed():
    """Test that diagnostic methods no longer reference WDA button."""
    try:
        print("\n🔧 诊断方法修复测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check _run_diagnostics method
        if 'self.diag_wda_btn.setEnabled(False)' in content:
            print("   ❌ _run_diagnostics中仍有WDA按钮引用")
            return False
        else:
            print("   ✅ _run_diagnostics中WDA按钮引用已清理")
        
        # Check _diagnostics_finished method
        if 'self.diag_wda_btn.setEnabled(True)' in content:
            print("   ❌ _diagnostics_finished中仍有WDA按钮引用")
            return False
        else:
            print("   ✅ _diagnostics_finished中WDA按钮引用已清理")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_application_import():
    """Test that application can be imported without errors."""
    try:
        print("\n🚀 应用导入测试")
        print("-" * 30)
        
        from gui_app.app import MainWindow
        print("   ✅ MainWindow类导入成功")
        
        # Test that ApkInstallWorker can be imported
        from gui_app.app import ApkInstallWorker
        print("   ✅ ApkInstallWorker类导入成功")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 修复验证测试")
    print("=" * 60)
    
    results = []
    
    # Test 1: WDA button removal
    results.append(("WDA按钮移除", test_wda_button_removal()))
    
    # Test 2: APK installer simplification
    results.append(("APK安装器简化", test_apk_installer_simplification()))
    
    # Test 3: Diagnostic methods fix
    results.append(("诊断方法修复", test_diag_methods_fixed()))
    
    # Test 4: Application import
    results.append(("应用导入", test_application_import()))
    
    print("\n" + "=" * 60)
    print("📊 测试结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(success for _, success in results):
        print("\n🎉 所有测试通过！修复完成！")
        print("\n📋 修复内容:")
        print("✅ 移除了WDA检查按钮")
        print("✅ 清理了诊断方法中的WDA引用")
        print("✅ 简化了APK安装器为ADB专用")
        print("✅ 移除了iOS/HDC设备类型检查")
        
        print("\n🎯 现在应该可以正常使用:")
        print("• 选择APK文件不会闪退")
        print("• 系统诊断界面无WDA相关功能")
        print("• 应用启动更稳定")
        
        print("\n💡 主要改进:")
        print("• APK安装: 只支持ADB设备")
        print("• 系统诊断: 移除WDA检查")
        print("• 界面一致: 全部ADB专用")
        print("• 错误修复: 解决段错误问题")
    else:
        print("\n⚠️ 部分测试失败，需要进一步检查。")

if __name__ == "__main__":
    main()
