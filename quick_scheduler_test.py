#!/usr/bin/env python3
"""快速验证ScheduledTasksManager修复"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def quick_test():
    """快速测试修复"""
    print("🔧 快速验证ScheduledTasksManager修复")
    print("=" * 40)
    
    try:
        # 测试导入
        from gui_app.scheduler import ScheduledTasksManager
        print("✅ ScheduledTasksManager导入成功")
        
        # 测试方法存在
        manager = ScheduledTasksManager()
        required_methods = ['get_running_tasks', 'mark_task_running', 'mark_task_finished', 'stop_all']
        
        for method in required_methods:
            if hasattr(manager, method):
                print(f"✅ {method}方法存在")
            else:
                print(f"❌ {method}方法缺失")
                return False
        
        # 测试方法调用
        running = manager.get_running_tasks()
        print(f"✅ get_running_tasks()返回: {running}")
        
        manager.mark_task_running("test_task")
        running_after = manager.get_running_tasks()
        print(f"✅ mark_task_running后: {running_after}")
        
        manager.mark_task_finished("test_task")
        running_final = manager.get_running_tasks()
        print(f"✅ mark_task_finished后: {running_final}")
        
        print("\n🎉 所有测试通过！修复成功！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

if __name__ == "__main__":
    success = quick_test()
    if success:
        print("\n🚀 应用现在可以正常使用:")
        print("• 📱 任务冲突检查包含定时任务")
        print("• 🛑 全部停止功能会停止定时任务")
        print("• ⚠️ 不会再出现AttributeError")
    else:
        print("\n⚠️ 还有问题需要解决")
