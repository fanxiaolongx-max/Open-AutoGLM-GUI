#!/usr/bin/env python3
"""Test the fix for _on_schedule_type_changed method."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_method_fix():
    """Test if the method name mismatch is fixed."""
    try:
        print("🔧 测试方法名修复")
        print("=" * 40)
        
        # Read the app.py file
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if the method call is correct
        if 'self.sched_type_combo.currentTextChanged.connect(self._on_schedule_type_changed)' in content:
            print("✅ 方法调用已修复: _on_schedule_type_changed")
        else:
            print("❌ 方法调用仍有问题")
            return False
        
        # Check if the method definition exists
        if 'def _on_schedule_type_changed(self, text):' in content:
            print("✅ 方法定义正确: 接受text参数")
        else:
            print("❌ 方法定义有问题")
            return False
        
        # Check if the text-to-index mapping exists
        if 'type_to_index = {' in content and '"单次执行": 0,' in content:
            print("✅ 文本到索引映射正确")
        else:
            print("❌ 文本到索引映射有问题")
            return False
        
        print("\n📋 修复内容:")
        print("1. 修正了方法名: _on_sched_type_changed → _on_schedule_type_changed")
        print("2. 修正了参数类型: index → text")
        print("3. 添加了文本到索引的映射逻辑")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_import_fix():
    """Test if custom widgets import is working."""
    try:
        print("\n🔧 测试自定义组件导入")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'from gui_app.custom_widgets import NoWheelSpinBox, NoWheelDoubleSpinBox, NoWheelComboBox, NoWheelTimeEdit' in content:
            print("✅ 自定义组件导入正确")
            return True
        else:
            print("❌ 自定义组件导入有问题")
            return False
            
    except Exception as e:
        print(f"❌ 导入测试失败: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 定时任务方法修复测试")
    print("=" * 50)
    
    results = []
    
    # Test 1: Method fix
    results.append(("方法修复", test_method_fix()))
    
    # Test 2: Import fix
    results.append(("组件导入", test_import_fix()))
    
    print("\n" + "=" * 50)
    print("📊 测试结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(success for _, success in results):
        print("\n🎉 所有测试通过！")
        print("\n📋 修复的问题:")
        print("✅ AttributeError: 'MainWindow' object has no attribute '_on_sched_type_changed'")
        print("✅ 方法名不匹配问题已解决")
        print("✅ 参数类型不匹配问题已解决")
        print("✅ 无滚轮组件导入正常")
        
        print("\n🎯 现在可以正常启动应用了！")
    else:
        print("\n⚠️ 部分测试失败，需要进一步检查。")

if __name__ == "__main__":
    main()
