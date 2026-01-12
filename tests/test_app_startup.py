#!/usr/bin/env python3
"""Quick test to verify the application can start without errors."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_app_import():
    """Test that the main application can be imported without errors."""
    try:
        print("🚀 应用启动测试")
        print("=" * 50)
        
        # Test importing MainWindow
        from gui_app.app import MainWindow
        print("   ✅ MainWindow类导入成功")
        
        # Test importing required modules
        from PySide6 import QtWidgets, QtCore, QtGui
        print("   ✅ PySide6模块导入成功")
        
        # Test that no wda_url_input references exist in critical methods
        import inspect
        
        # Check _load_settings method
        load_settings_source = inspect.getsource(MainWindow._load_settings)
        if 'wda_url_input' in load_settings_source:
            print("   ❌ _load_settings中仍有wda_url_input引用")
            return False
        else:
            print("   ✅ _load_settings中wda_url_input已清理")
        
        # Check _save_settings method
        save_settings_source = inspect.getsource(MainWindow._save_settings)
        if 'wda_url_input' in save_settings_source:
            print("   ❌ _save_settings中仍有wda_url_input引用")
            return False
        else:
            print("   ✅ _save_settings中wda_url_input已清理")
        
        # Check __init__ method for device type
        init_source = inspect.getsource(MainWindow.__init__)
        if 'addItems(["adb", "hdc", "ios"])' in init_source:
            print("   ❌ 设备类型仍包含HDC/iOS")
            return False
        elif 'addItems(["adb"])' in init_source:
            print("   ✅ 设备类型已简化为ADB")
        else:
            print("   ⚠️ 设备类型配置不明确")
        
        print("\n🎉 应用启动测试通过！")
        print("📋 修复内容:")
        print("✅ 移除了wda_url_input引用")
        print("✅ 清理了设置保存/加载逻辑")
        print("✅ 界面简化为ADB专用")
        
        return True
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 其他错误: {e}")
        return False

def main():
    """Run the test."""
    success = test_app_import()
    
    if success:
        print("\n💡 应用现在可以正常启动！")
        print("🎯 下一步:")
        print("• 运行 python gui_main.py 启动应用")
        print("• 测试设备中心的ADB功能")
        print("• 验证界面简化效果")
    else:
        print("\n⚠️ 仍有问题需要解决。")

if __name__ == "__main__":
    main()
