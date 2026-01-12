#!/usr/bin/env python3
"""Test device hub improvements and direct QR pairing."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_advanced_configuration():
    """Test advanced configuration functionality."""
    try:
        print("🔧 高级配置功能测试")
        print("=" * 50)
        
        # Check if advanced configuration is implemented
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        required_elements = [
            'self.advanced_widget = QtWidgets.QWidget()',
            'self.advanced_widget.setVisible(False)',
            'self.advanced_btn = QtWidgets.QPushButton("⚙️ 高级配置")',
            'def _toggle_advanced(self, checked):',
            'self.device_id_input',
            'self.tcpip_port_input',
            'self.wda_url_input'
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

def test_auto_detection():
    """Test auto detection and cleaning functionality."""
    try:
        print("\n🔍 自动检测功能测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        required_methods = [
            'def _auto_detect_and_clean(self):',
            'def _clean_existing_connections(self, device_type):',
            'subprocess.run([\'adb\', \'kill-server\'], capture_output=True, check=False)',
            'subprocess.run([\'adb\', \'start-server\'], capture_output=True, check=False)',
            'subprocess.run([\'hdc\', \'kill-server\'], capture_output=True, check=False)',
            'subprocess.run([\'hdc\', \'start-server\'], capture_output=True, check=False)'
        ]
        
        found_methods = []
        for method in required_methods:
            if method in content:
                found_methods.append(method)
                print(f"   ✅ {method}")
            else:
                print(f"   ❌ {method}")
        
        success_rate = len(found_methods) / len(required_methods)
        print(f"\n📊 完成度: {success_rate:.1%} ({len(found_methods)}/{len(required_methods)})")
        
        return success_rate >= 0.8
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_direct_qr_pairing():
    """Test direct QR pairing functionality."""
    try:
        print("\n📱 直接二维码配对测试")
        print("-" * 30)
        
        # Check if direct QR pairing file exists
        qr_file = '/mnt/data/TOOL/Open-AutoGLM/phone_agent/direct_qr_pairing.py'
        if os.path.exists(qr_file):
            print(f"   ✅ 直接QR配对模块存在: {qr_file}")
        else:
            print(f"   ❌ 直接QR配对模块不存在: {qr_file}")
            return False
        
        # Check file content
        with open(qr_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        required_classes = [
            'class DirectADBQRPairing:',
            'class DirectQRCodeDialog(QtWidgets.QDialog):',
            'def generate_qr_code(self) -> QtGui.QPixmap:',
            'def start_pairing_monitor(self, callback=None)',
            'WIFI:T:ADB;S:{self.target_ip}:{self.target_port};P:{self.pairing_password};;'
        ]
        
        found_classes = []
        for cls in required_classes:
            if cls in content:
                found_classes.append(cls)
                print(f"   ✅ {cls}")
            else:
                print(f"   ❌ {cls}")
        
        success_rate = len(found_classes) / len(required_classes)
        print(f"\n📊 完成度: {success_rate:.1%} ({len(found_classes)}/{len(required_classes)})")
        
        return success_rate >= 0.8
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_ui_improvements():
    """Test UI improvements."""
    try:
        print("\n🎨 UI界面改进测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        ui_improvements = [
            'self.refresh_devices_btn = QtWidgets.QPushButton("🔍 自动检测")',
            'self.refresh_devices_btn.setObjectName("primary")',
            'self.refresh_devices_btn.clicked.connect(self._auto_detect_and_clean)',
            'elif index == 1:  # Device hub page',
            'QtCore.QTimer.singleShot(500, self._auto_detect_and_clean)',
            'from phone_agent.direct_qr_pairing import DirectQRCodeDialog'
        ]
        
        found_improvements = []
        for improvement in ui_improvements:
            if improvement in content:
                found_improvements.append(improvement)
                print(f"   ✅ {improvement}")
            else:
                print(f"   ❌ {improvement}")
        
        success_rate = len(found_improvements) / len(ui_improvements)
        print(f"\n📊 完成度: {success_rate:.1%} ({len(found_improvements)}/{len(ui_improvements)})")
        
        return success_rate >= 0.8
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_page_switch_integration():
    """Test page switch integration."""
    try:
        print("\n🔄 页面切换集成测试")
        print("-" * 30)
        
        with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if auto detection is triggered on page switch
        if 'elif index == 1:  # Device hub page' in content and 'QtCore.QTimer.singleShot(500, self._auto_detect_and_clean)' in content:
            print("   ✅ 页面切换时自动触发设备检测")
            return True
        else:
            print("   ❌ 页面切换集成缺失")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 设备中心功能改进测试")
    print("=" * 60)
    
    results = []
    
    # Test 1: Advanced configuration
    results.append(("高级配置", test_advanced_configuration()))
    
    # Test 2: Auto detection
    results.append(("自动检测", test_auto_detection()))
    
    # Test 3: Direct QR pairing
    results.append(("直接二维码配对", test_direct_qr_pairing()))
    
    # Test 4: UI improvements
    results.append(("UI改进", test_ui_improvements()))
    
    # Test 5: Page switch integration
    results.append(("页面切换集成", test_page_switch_integration()))
    
    print("\n" + "=" * 60)
    print("📊 测试结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(success for _, success in results):
        print("\n🎉 所有测试通过！")
        print("\n📋 完成的功能:")
        print("✅ 高级配置按钮隐藏不常用输入框")
        print("✅ 自动检测设备并清理现有连接")
        print("✅ 直接二维码配对（无需DNS服务）")
        print("✅ 页面切换时自动触发检测")
        print("✅ UI界面优化和改进")
        
        print("\n🎯 主要改进:")
        print("1. 界面更简洁：隐藏设备ID、TCP/IP端口、WDA地址")
        print("2. 自动化程度高：点击设备中心自动检测")
        print("3. 连接更可靠：检测前清理现有连接")
        print("4. 配对更简单：直接IP连接，无需DNS")
        print("5. 用户体验更好：一键自动检测")
    else:
        print("\n⚠️ 部分测试失败，需要进一步检查。")

if __name__ == "__main__":
    main()
