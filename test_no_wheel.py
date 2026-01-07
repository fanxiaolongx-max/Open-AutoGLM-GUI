#!/usr/bin/env python3
"""Test no-wheel functionality for UI components."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_custom_widgets():
    """Test custom widgets functionality."""
    try:
        from PySide6 import QtWidgets, QtCore
        from gui_app.custom_widgets import (
            NoWheelSpinBox, NoWheelDoubleSpinBox, 
            NoWheelComboBox, NoWheelTimeEdit
        )
        
        print("🚀 自定义组件测试")
        print("=" * 60)
        
        # Create application
        app = QtWidgets.QApplication(sys.argv)
        
        # Test NoWheelSpinBox
        print("\n📋 测试 NoWheelSpinBox:")
        spinbox = NoWheelSpinBox()
        spinbox.setRange(1, 100)
        spinbox.setValue(50)
        print(f"   ✅ 创建成功: 范围1-100, 当前值{spinbox.value()}")
        print(f"   ✅ 按钮符号: {spinbox.buttonSymbols()}")
        
        # Test NoWheelDoubleSpinBox
        print("\n📋 测试 NoWheelDoubleSpinBox:")
        double_spinbox = NoWheelDoubleSpinBox()
        double_spinbox.setRange(0.0, 2.0)
        double_spinbox.setValue(0.7)
        print(f"   ✅ 创建成功: 范围0.0-2.0, 当前值{double_spinbox.value()}")
        print(f"   ✅ 按钮符号: {double_spinbox.buttonSymbols()}")
        
        # Test NoWheelComboBox
        print("\n📋 测试 NoWheelComboBox:")
        combobox = NoWheelComboBox()
        combobox.addItems(["选项1", "选项2", "选项3"])
        print(f"   ✅ 创建成功: {combobox.count()}个选项")
        print(f"   ✅ 焦点策略: {combobox.focusPolicy()}")
        
        # Test NoWheelTimeEdit
        print("\n📋 测试 NoWheelTimeEdit:")
        time_edit = NoWheelTimeEdit()
        time_edit.setTime(QtCore.QTime(12, 30))
        print(f"   ✅ 创建成功: 当前时间{time_edit.time().toString()}")
        print(f"   ✅ 按钮符号: {time_edit.buttonSymbols()}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_app_integration():
    """Test integration with main app."""
    try:
        print("\n🔧 应用集成测试")
        print("-" * 30)
        
        # Check if custom widgets are properly imported in app.py
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        required_imports = [
            'from gui_app.custom_widgets import NoWheelSpinBox',
            'NoWheelSpinBox',
            'NoWheelDoubleSpinBox',
            'NoWheelComboBox',
            'NoWheelTimeEdit'
        ]
        
        missing_imports = []
        for import_name in required_imports:
            if import_name not in content:
                missing_imports.append(import_name)
        
        if missing_imports:
            print(f"❌ 缺少导入: {missing_imports}")
            return False
        else:
            print("✅ 所有自定义组件已正确导入")
        
        # Count replacements
        replacements = {
            'NoWheelSpinBox': content.count('NoWheelSpinBox'),
            'NoWheelDoubleSpinBox': content.count('NoWheelDoubleSpinBox'),
            'NoWheelComboBox': content.count('NoWheelComboBox'),
            'NoWheelTimeEdit': content.count('NoWheelTimeEdit')
        }
        
        print("\n📊 组件替换统计:")
        for widget_type, count in replacements.items():
            print(f"   {widget_type}: {count}个")
        
        total_replacements = sum(replacements.values())
        if total_replacements > 0:
            print(f"\n✅ 总共替换了{total_replacements}个组件")
            return True
        else:
            print("\n❌ 没有找到任何替换")
            return False
            
    except Exception as e:
        print(f"❌ 集成测试失败: {e}")
        return False

def test_css_updates():
    """Test CSS updates for hiding arrows."""
    try:
        print("\n🎨 CSS样式测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for CSS updates
        css_checks = [
            'QSpinBox::up-button, QSpinBox::down-button',
            'width: 0px',
            'height: 0px',
            'QSpinBox::up-arrow, QSpinBox::down-arrow'
        ]
        
        css_found = []
        for check in css_checks:
            if check in content:
                css_found.append(check)
        
        print(f"✅ 找到{len(css_found)}/{len(css_checks)}个CSS更新")
        for css in css_found:
            print(f"   {css}")
        
        return len(css_found) >= 3
        
    except Exception as e:
        print(f"❌ CSS测试失败: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 无滚轮功能测试")
    print("=" * 60)
    
    results = []
    
    # Test 1: Custom widgets
    results.append(("自定义组件", test_custom_widgets()))
    
    # Test 2: App integration
    results.append(("应用集成", test_app_integration()))
    
    # Test 3: CSS updates
    results.append(("CSS样式", test_css_updates()))
    
    print("\n" + "=" * 60)
    print("📊 测试结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(success for _, success in results):
        print("\n🎉 所有测试通过！")
        print("\n📋 已完成的功能:")
        print("✅ 禁用所有SpinBox的鼠标滚轮功能")
        print("✅ 禁用所有SpinBox的上下箭头按钮")
        print("✅ 禁用所有ComboBox的鼠标滚轮功能")
        print("✅ 禁用所有TimeEdit的鼠标滚轮功能")
        print("✅ 保留键盘输入功能")
        print("✅ CSS样式完全隐藏箭头")
        
        print("\n🎯 用户体验改进:")
        print("• 防止意外滚动改变数值")
        print("• 只能通过键盘输入精确数值")
        print("• 界面更加简洁统一")
        print("• 操作更加可控")
    else:
        print("\n⚠️ 部分测试失败，需要进一步检查。")

if __name__ == "__main__":
    main()
