#!/usr/bin/env python3
"""Final verification of Gemini API configuration in GUI."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def main():
    """Final verification test."""
    print("🎯 Gemini API 配置最终验证")
    print("=" * 60)
    
    try:
        from gui_app.model_services import ModelServicesManager
        
        # Load services
        manager = ModelServicesManager()
        services = manager.get_all_services()
        
        # Find Gemini service
        gemini_service = None
        for service in services:
            if service.id == "gemini_antigravity":
                gemini_service = service
                break
        
        if not gemini_service:
            print("❌ Gemini服务未找到")
            return False
        
        print("✅ Gemini服务配置:")
        print(f"   名称: {gemini_service.name}")
        print(f"   地址: {gemini_service.base_url}")
        print(f"   模型: {gemini_service.model_name}")
        print(f"   密钥: {gemini_service.api_key[:8]}...")
        print(f"   温度: {gemini_service.temperature}")
        print(f"   最大令牌: {gemini_service.max_tokens}")
        print(f"   激活状态: {'是' if gemini_service.is_active else '否'}")
        
        # Test connection
        print("\n🔧 测试连接...")
        success, message = manager.test_service(gemini_service)
        
        if success:
            print("✅ 连接测试成功!")
            print(f"📝 消息: {message}")
            
            print("\n🎉 配置验证完成!")
            print("\n📋 使用步骤:")
            print("1. 启动AutoGLM GUI应用")
            print("2. 进入'模型服务'页面")
            print("3. 在服务列表中选择'Gemini (Antigravity代理)'")
            print("4. 点击'激活'按钮")
            print("5. 点击'测试连接'验证配置")
            print("6. 成功后即可在任务执行中使用Gemini模型")
            
            return True
        else:
            print("❌ 连接测试失败!")
            print(f"📝 错误: {message}")
            return False
            
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
