#!/usr/bin/env python3
"""Test GUI model service functionality."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_gui_model_service():
    """Test the GUI model service test functionality."""
    try:
        from gui_app.model_services import ModelServicesManager, ModelServiceConfig
        
        print("🔧 测试GUI模型服务功能...")
        print("-" * 50)
        
        # Create manager
        manager = ModelServicesManager()
        
        # Create a test service config (same as GUI would create)
        temp_service = ModelServiceConfig(
            id="temp",
            name="Gemini (Antigravity代理)",
            base_url="http://127.0.0.1:8045/v1",
            api_key="sk-985786ae787d43e6b8d42688f39ed83a",
            model_name="gemini-3-pro-high",
        )
        
        print("📋 测试服务配置:")
        print(f"   名称: {temp_service.name}")
        print(f"   地址: {temp_service.base_url}")
        print(f"   模型: {temp_service.model_name}")
        print(f"   密钥: {temp_service.api_key[:8]}...")
        
        print("\n🔍 调用test_service方法...")
        success, message = manager.test_service(temp_service)
        
        print(f"📊 测试结果: {'成功' if success else '失败'}")
        print(f"📝 返回消息: {message}")
        
        # Simulate GUI status update
        if success:
            status_text = f"✓ {message}"
            status_style = "color: #10b981; background: rgba(16, 185, 129, 0.15);"
        else:
            status_text = f"✗ {message}"
            status_style = "color: #ef4444; background: rgba(239, 68, 68, 0.15);"
        
        print(f"\n🎨 GUI状态显示:")
        print(f"   文本: {status_text}")
        print(f"   样式: {status_style}")
        
        return success
        
    except Exception as e:
        print(f"❌ GUI模型服务测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_service_loading():
    """Test if services are loaded correctly in GUI context."""
    try:
        from gui_app.model_services import ModelServicesManager
        
        print("\n🔧 测试服务加载...")
        print("-" * 50)
        
        manager = ModelServicesManager()
        services = manager.get_all_services()
        
        print(f"📊 已加载服务数量: {len(services)}")
        for service in services:
            prefix = "✓ " if service.is_active else "  "
            print(f"   {prefix}{service.name} ({service.id})")
        
        # Check if Gemini service exists
        gemini_found = any(s.id == "gemini_antigravity" for s in services)
        if gemini_found:
            print("✅ Gemini服务已加载")
        else:
            print("⚠️ Gemini服务未在已加载服务中找到")
            print("🔍 检查预置模板...")
            presets = manager.get_preset_templates()
            gemini_preset_found = any(p.id == "gemini_antigravity" for p in presets)
            if gemini_preset_found:
                print("✅ Gemini服务在预置模板中找到")
            else:
                print("❌ Gemini服务在预置模板中未找到")
        
        return gemini_found or gemini_preset_found
        
    except Exception as e:
        print(f"❌ 服务加载测试失败: {e}")
        return False

def main():
    """Run all GUI tests."""
    print("🚀 GUI模型服务测试")
    print("=" * 60)
    
    results = []
    
    # Test 1: Service loading
    results.append(("服务加载", test_service_loading()))
    
    # Test 2: GUI model service test
    results.append(("GUI测试功能", test_gui_model_service()))
    
    print("\n" + "=" * 60)
    print("📊 GUI测试结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all(success for _, success in results):
        print("\n🎉 GUI测试通过！")
        print("如果仍然显示失败，请检查:")
        print("1. GUI中是否选择了正确的服务")
        print("2. 表单中的配置是否正确")
        print("3. 网络连接是否正常")
    else:
        print("\n⚠️ GUI测试失败，需要进一步排查。")

if __name__ == "__main__":
    main()
