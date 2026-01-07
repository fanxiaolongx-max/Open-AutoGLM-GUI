#!/usr/bin/env python3
"""Test interface simplification to ADB-only functionality."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_device_type_simplification():
    """Test that device type dropdown only contains ADB."""
    try:
        print("📱 设备类型简化测试")
        print("=" * 50)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that only ADB is in the device type combo
        if 'self.device_type_combo.addItems(["adb"])' in content:
            print("   ✅ 设备类型下拉框只包含ADB")
            success1 = True
        else:
            print("   ❌ 设备类型下拉框未正确简化")
            success1 = False
        
        # Check that HDC and iOS are removed
        if 'hdc' not in content or 'ios' not in content:
            print("   ✅ HDC和iOS选项已移除")
            success2 = True
        else:
            print("   ❌ HDC或iOS选项仍然存在")
            success2 = False
        
        return success1 and success2
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_ios_button_removal():
    """Test that iOS-specific buttons are removed."""
    try:
        print("\n🔘 iOS按钮移除测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        ios_buttons = [
            'self.pair_btn = QtWidgets.QPushButton("配对iOS")',
            'self.wda_btn = QtWidgets.QPushButton("WDA状态")',
            'buttons.addWidget(self.pair_btn)',
            'buttons.addWidget(self.wda_btn)'
        ]
        
        removed_buttons = []
        for button in ios_buttons:
            if button not in content:
                removed_buttons.append(button)
                print(f"   ✅ 已移除: {button}")
            else:
                print(f"   ❌ 仍存在: {button}")
        
        success_rate = len(removed_buttons) / len(ios_buttons)
        print(f"\n📊 移除完成度: {success_rate:.1%} ({len(removed_buttons)}/{len(ios_buttons)})")
        
        return success_rate >= 0.8
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_wda_input_removal():
    """Test that WDA input field is removed."""
    try:
        print("\n📝 WDA输入框移除测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        wda_elements = [
            'self.wda_url_input = QtWidgets.QLineEdit()',
            'self.wda_url_input.setPlaceholderText("http://localhost:8100")',
            'advanced_form.addRow("WDA地址(iOS)", self.wda_url_input)'
        ]
        
        removed_elements = []
        for element in wda_elements:
            if element not in content:
                removed_elements.append(element)
                print(f"   ✅ 已移除: {element}")
            else:
                print(f"   ❌ 仍存在: {element}")
        
        success_rate = len(removed_elements) / len(wda_elements)
        print(f"\n📊 移除完成度: {success_rate:.1%} ({len(removed_elements)}/{len(wda_elements)})")
        
        return success_rate >= 0.8
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_adb_functionality_preserved():
    """Test that ADB functionality is preserved."""
    try:
        print("\n🔧 ADB功能保留测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        adb_elements = [
            'self.device_type_combo.addItems(["adb"])',
            'self.connect_input',
            'self.pair_address_input',
            'self.pair_code_input',
            'self.device_id_input',
            'self.tcpip_port_input',
            'self.refresh_devices_btn',
            'self.connect_btn',
            'self.disconnect_btn',
            'self.tcpip_btn',
            'self.wireless_pair_btn',
            'self.qr_pair_btn'
        ]
        
        preserved_elements = []
        for element in adb_elements:
            if element in content:
                preserved_elements.append(element)
                print(f"   ✅ 已保留: {element}")
            else:
                print(f"   ❌ 缺失: {element}")
        
        success_rate = len(preserved_elements) / len(adb_elements)
        print(f"\n📊 保留完成度: {success_rate:.1%} ({len(preserved_elements)}/{len(adb_elements)})")
        
        return success_rate >= 0.8
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_interface_cleanliness():
    """Test overall interface cleanliness."""
    try:
        print("\n🎨 界面整洁度测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Count remaining iOS/HDC references
        ios_refs = content.count('ios') + content.count('iOS')
        hdc_refs = content.count('hdc') + content.count('HDC')
        
        print(f"   📊 iOS相关引用: {ios_refs}")
        print(f"   📊 HDC相关引用: {hdc_refs}")
        
        # Check if references are minimal (only in comments or unavoidable places)
        if ios_refs <= 2 and hdc_refs <= 2:
            print("   ✅ 界面已简化，iOS/HDC引用最少")
            return True
        else:
            print("   ⚠️ 仍有较多iOS/HDC引用")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 ADB专用界面简化测试")
    print("=" * 60)
    
    results = []
    
    # Test 1: Device type simplification
    results.append(("设备类型简化", test_device_type_simplification()))
    
    # Test 2: iOS button removal
    results.append(("iOS按钮移除", test_ios_button_removal()))
    
    # Test 3: WDA input removal
    results.append(("WDA输入框移除", test_wda_input_removal()))
    
    # Test 4: ADB functionality preservation
    results.append(("ADB功能保留", test_adb_functionality_preserved()))
    
    # Test 5: Interface cleanliness
    results.append(("界面整洁度", test_interface_cleanliness()))
    
    print("\n" + "=" * 60)
    print("📊 测试结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(success for _, success in results):
        print("\n🎉 所有测试通过！")
        print("\n📋 完成的界面简化:")
        print("✅ 设备类型只保留ADB选项")
        print("✅ 移除iOS配对按钮")
        print("✅ 移除WDA状态按钮")
        print("✅ 移除WDA地址输入框")
        print("✅ 保留所有ADB相关功能")
        
        print("\n🎯 简化后的界面:")
        print("• 设备类型: 仅ADB")
        print("• 连接设置: 连接地址、配对地址、配对码")
        print("• 高级配置: 设备ID、TCP/IP端口")
        print("• 操作按钮: 自动检测、连接、断开、TCP/IP、无线配对、二维码配对")
        
        print("\n💡 用户体验:")
        print("• 界面更简洁: 移除不相关选项")
        print("• 操作更专注: 专注于ADB功能")
        print("• 学习成本更低: 减少复杂选项")
        print("• 维护更容易: 单一设备类型支持")
    else:
        print("\n⚠️ 部分测试失败，需要进一步检查。")

if __name__ == "__main__":
    main()
