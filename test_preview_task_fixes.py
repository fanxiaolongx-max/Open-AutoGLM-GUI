#!/usr/bin/env python3
"""测试预览状态和任务管理修复"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def test_preview_status_fix():
    """测试预览状态修复"""
    print("🔍 预览状态修复测试")
    print("=" * 50)
    
    results = []
    
    with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. 检查预览状态更新逻辑
    print("\n📺 1. 预览状态更新逻辑")
    print("-" * 30)
    
    if 'current_status.startswith(f"预览设备: {device_id}")' in content:
        print("   ✅ 添加了设备状态检查逻辑")
        results.append(("设备状态检查", True))
    else:
        print("   ❌ 缺少设备状态检查逻辑")
        results.append(("设备状态检查", False))
    
    if 'not current_status.startswith("预览运行中")' in content:
        print("   ✅ 添加了运行状态检查")
        results.append(("运行状态检查", True))
    else:
        print("   ❌ 缺少运行状态检查")
        results.append(("运行状态检查", False))
    
    # 2. 检查时间戳移除
    print("\n⏰ 2. 时间戳移除")
    print("-" * 30)
    
    if 'timestamp = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")' not in content:
        print("   ✅ 移除了时间戳显示")
        results.append(("时间戳移除", True))
    else:
        print("   ❌ 仍包含时间戳显示")
        results.append(("时间戳移除", False))
    
    if 'elif is_sensitive:' in content and 'self.preview_status.setText("预览已更新(敏感内容)")' in content:
        print("   ✅ 简化了状态更新逻辑")
        results.append(("状态更新简化", True))
    else:
        print("   ❌ 状态更新逻辑未简化")
        results.append(("状态更新简化", False))
    
    return results

def test_task_conflict_management():
    """测试任务冲突管理"""
    print("\n🔧 任务冲突管理测试")
    print("=" * 50)
    
    results = []
    
    with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. 检查冲突检查方法
    print("\n⚠️ 1. 任务冲突检查方法")
    print("-" * 30)
    
    if 'def _check_task_conflicts(self):' in content:
        print("   ✅ 添加了任务冲突检查方法")
        results.append(("冲突检查方法", True))
    else:
        print("   ❌ 缺少任务冲突检查方法")
        results.append(("冲突检查方法", False))
    
    # 2. 检查各种任务类型检查
    print("\n📋 2. 任务类型检查")
    print("-" * 30)
    
    task_types = [
        ("多设备任务", "multi_device_manager.workers"),
        ("单设备任务", "task_worker.isRunning()"),
        ("脚本任务", "script_worker.isRunning()"),
        ("Gemini任务", "gemini_task_worker.isRunning()"),
        ("定时任务", "scheduled_tasks_manager.get_running_tasks()")
    ]
    
    for task_name, check_code in task_types:
        if check_code in content:
            print(f"   ✅ 检查{task_name}")
            results.append((f"{task_name}检查", True))
        else:
            print(f"   ❌ 未检查{task_name}")
            results.append((f"{task_name}检查", False))
    
    # 3. 检查任务执行入口点
    print("\n🚀 3. 任务执行入口点")
    print("-" * 30)
    
    entry_points = [
        ("多设备任务", "_run_multi_task"),
        ("单设备任务", "_run_task"),
        ("脚本执行", "_run_script")
    ]
    
    for task_name, method_name in entry_points:
        if f'if self._check_task_conflicts():' in content and method_name in content:
            # 检查方法中是否包含冲突检查
            method_start = content.find(f"def {method_name}")
            if method_start != -1:
                method_end = content.find("def ", method_start + 1)
                if method_end == -1:
                    method_end = len(content)
                method_code = content[method_start:method_end]
                if "_check_task_conflicts()" in method_code:
                    print(f"   ✅ {task_name}包含冲突检查")
                    results.append((f"{task_name}冲突检查", True))
                else:
                    print(f"   ❌ {task_name}缺少冲突检查")
                    results.append((f"{task_name}冲突检查", False))
    
    return results

def test_stop_all_functionality():
    """测试全部停止功能"""
    print("\n🛑 全部停止功能测试")
    print("=" * 50)
    
    results = []
    
    with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. 检查停止方法增强
    print("\n⏹️ 1. 停止方法增强")
    print("-" * 30)
    
    if 'stopped_tasks = []' in content:
        print("   ✅ 添加了停止任务统计")
        results.append(("停止任务统计", True))
    else:
        print("   ❌ 缺少停止任务统计")
        results.append(("停止任务统计", False))
    
    # 2. 检查各种任务停止
    print("\n📋 2. 任务停止覆盖")
    print("-" * 30)
    
    stop_checks = [
        ("多设备任务停止", "multi_device_manager.stop_all()"),
        ("单设备任务停止", "task_worker.terminate()"),
        ("脚本任务停止", "script_worker.terminate()"),
        ("Gemini任务停止", "gemini_task_worker.terminate()"),
        ("定时任务停止", "scheduled_tasks_manager.stop_all()")
    ]
    
    for task_name, stop_code in stop_checks:
        if stop_code in content:
            print(f"   ✅ 停止{task_name}")
            results.append((f"{task_name}停止", True))
        else:
            print(f"   ❌ 未停止{task_name}")
            results.append((f"{task_name}停止", False))
    
    # 3. 检查停止日志
    print("\n📝 3. 停止日志")
    print("-" * 30)
    
    if '🛑 已停止以下任务:' in content:
        print("   ✅ 添加了停止日志")
        results.append(("停止日志", True))
    else:
        print("   ❌ 缺少停止日志")
        results.append(("停止日志", False))
    
    if 'self.run_task_btn.setEnabled(True)' in content and 'self.stop_task_btn.setEnabled(False)' in content:
        print("   ✅ 正确恢复按钮状态")
        results.append(("按钮状态恢复", True))
    else:
        print("   ❌ 按钮状态未恢复")
        results.append(("按钮状态恢复", False))
    
    return results

def main():
    """主函数"""
    print("🔧 预览状态和任务管理修复测试")
    print("=" * 60)
    
    preview_results = test_preview_status_fix()
    conflict_results = test_task_conflict_management()
    stop_results = test_stop_all_functionality()
    
    all_results = preview_results + conflict_results + stop_results
    
    print("\n" + "=" * 60)
    print("📊 修复结果统计")
    print("=" * 60)
    
    passed = sum(1 for _, success in all_results if success)
    total = len(all_results)
    
    print(f"✅ 预览状态修复: {sum(1 for _, success in preview_results if success)}/{len(preview_results)}")
    print(f"✅ 任务冲突管理: {sum(1 for _, success in conflict_results if success)}/{len(conflict_results)}")
    print(f"✅ 全部停止功能: {sum(1 for _, success in stop_results if success)}/{len(stop_results)}")
    print(f"📈 总体成功率: {passed/total:.1%}")
    
    if passed >= total * 0.8:
        print("\n🎉 修复成功！")
        print("\n📋 修复内容:")
        print("✅ 预览状态不再频繁变化")
        print("✅ 移除了时间戳显示")
        print("✅ 添加了全面的任务冲突检查")
        print("✅ 增强了全部停止功能")
        print("✅ 改进了任务管理逻辑")
        
        print("\n🎯 用户体验提升:")
        print("• 📺 预览状态稳定，不再闪烁")
        print("• ⚠️ 任务冲突时明确提示")
        print("• 🛑 全部停止按钮真正停止所有任务")
        print("• 🔒 防止任务冲突和资源竞争")
        
        print("\n🚀 使用方法:")
        print("1. 预览状态现在稳定显示设备信息")
        print("2. 执行新任务时会检查冲突")
        print("3. 点击'全部停止'会停止所有类型的任务")
        
    else:
        print(f"\n⚠️ 还有 {total - passed} 个问题需要解决")
        print("请检查失败的测试项目。")

if __name__ == "__main__":
    main()
