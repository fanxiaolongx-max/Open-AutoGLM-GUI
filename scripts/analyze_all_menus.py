#!/usr/bin/env python3
"""全面检查所有菜单的多设备兼容性"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/mnt/data/TOOL/Open-AutoGLM')

def analyze_all_menu_compatibility():
    """分析所有菜单的多设备兼容性"""
    print("🔍 全面多设备兼容性检查")
    print("=" * 60)
    
    with open('/mnt/data/TOOL/Open-AutoGLM/gui_app/app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 分析各个菜单页面
    menus = {
        "设备中心": {
            "功能": ["设备连接", "设备断开", "无线配对", "二维码配对", "TCP/IP启用"],
            "多设备支持": [],
            "问题": [],
            "建议": []
        },
        "任务执行": {
            "功能": ["任务执行", "实时预览", "设备选择"],
            "多设备支持": [],
            "问题": [],
            "建议": []
        },
        "定时任务": {
            "功能": ["定时任务执行", "任务调度"],
            "多设备支持": [],
            "问题": [],
            "建议": []
        },
        "应用安装": {
            "功能": ["APK安装", "拖拽安装"],
            "多设备支持": [],
            "问题": [],
            "建议": []
        },
        "脚本管理": {
            "功能": ["脚本执行"],
            "多设备支持": [],
            "问题": [],
            "建议": []
        },
        "应用目录": {
            "功能": ["应用启动"],
            "多设备支持": [],
            "问题": [],
            "建议": []
        },
        "系统诊断": {
            "功能": ["系统检查", "模型检查"],
            "多设备支持": [],
            "问题": [],
            "建议": []
        },
        "模型服务": {
            "功能": ["模型配置"],
            "多设备支持": [],
            "问题": [],
            "建议": []
        }
    }
    
    # 1. 设备中心页面分析
    print("\n📱 设备中心页面")
    print("-" * 30)
    
    # 检查设备连接功能
    if 'self.device_list.selectedItems()' in content and '_connect_device' in content:
        print("   ✅ 可以基于选中设备进行连接")
        menus["设备中心"]["多设备支持"].append("设备选择")
    else:
        print("   ❌ 连接功能未使用设备列表选择")
        menus["设备中心"]["问题"].append("连接功能未支持多设备选择")
        menus["设备中心"]["建议"].append("添加批量连接功能")
    
    # 检查设备列表交互
    if 'itemClicked.connect' in content and 'itemDoubleClicked.connect' in content:
        print("   ✅ 设备列表支持点击和双击交互")
        menus["设备中心"]["多设备支持"].append("设备交互")
    else:
        print("   ❌ 设备列表缺少交互事件")
        menus["设备中心"]["问题"].append("设备列表交互不完整")
    
    # 2. 任务执行页面分析
    print("\n⚡ 任务执行页面")
    print("-" * 30)
    
    # 检查任务执行多设备支持
    if 'task_device_list.selectedItems()' in content:
        print("   ✅ 任务执行支持多设备选择")
        menus["任务执行"]["多设备支持"].append("多设备任务")
    else:
        print("   ❌ 任务执行未支持多设备")
        menus["任务执行"]["问题"].append("任务执行未支持多设备")
    
    # 检查预览功能
    if '_get_selected_device_id()' in content and '_request_preview_frame' in content:
        print("   ✅ 预览功能支持多设备切换")
        menus["任务执行"]["多设备支持"].append("多设备预览")
    else:
        print("   ❌ 预览功能未支持多设备")
        menus["任务执行"]["问题"].append("预览功能未支持多设备")
    
    # 3. 定时任务页面分析
    print("\n⏰ 定时任务页面")
    print("-" * 30)
    
    # 检查定时任务多设备支持
    if 'scheduled_tasks' in content and 'device' in content.lower():
        print("   ⚠️ 定时任务可能需要多设备支持")
        menus["定时任务"]["问题"].append("定时任务未明确支持多设备")
        menus["定时任务"]["建议"].append("添加定时任务设备选择")
    else:
        print("   ❌ 定时任务缺少设备相关逻辑")
        menus["定时任务"]["问题"].append("定时任务缺少设备逻辑")
    
    # 4. 应用安装页面分析
    print("\n📱 应用安装页面")
    print("-" * 30)
    
    # 检查APK安装多设备支持
    if '_install_apk' in content and 'selectedItems()' in content:
        print("   ✅ APK安装可能支持多设备")
        menus["应用安装"]["多设备支持"].append("多设备安装")
    else:
        print("   ⚠️ APK安装可能需要多设备支持")
        menus["应用安装"]["建议"].append("添加多设备APK安装")
    
    # 检查拖拽安装
    if 'fileDropped' in content:
        print("   ✅ 支持拖拽安装")
        menus["应用安装"]["多设备支持"].append("拖拽安装")
    
    # 5. 脚本管理页面分析
    print("\n📜 脚本管理页面")
    print("-" * 30)
    
    # 检查脚本执行多设备支持
    if 'script' in content.lower() and 'selectedItems()' in content:
        print("   ✅ 脚本管理可能支持多设备")
        menus["脚本管理"]["多设备支持"].append("脚本执行")
    else:
        print("   ⚠️ 脚本执行可能需要多设备支持")
        menus["脚本管理"]["建议"].append("添加多设备脚本执行")
    
    # 6. 应用目录页面分析
    print("\n📚 应用目录页面")
    print("-" * 30)
    
    # 检查应用启动多设备支持
    if 'apps' in content.lower() and 'selectedItems()' in content:
        print("   ✅ 应用目录可能支持多设备")
        menus["应用目录"]["多设备支持"].append("应用启动")
    else:
        print("   ⚠️ 应用启动可能需要多设备支持")
        menus["应用目录"]["建议"].append("添加多设备应用启动")
    
    # 7. 系统诊断页面分析
    print("\n🔧 系统诊断页面")
    print("-" * 30)
    
    # 检查诊断多设备支持
    if 'diagnostic' in content.lower() and 'selectedItems()' in content:
        print("   ✅ 系统诊断可能支持多设备")
        menus["系统诊断"]["多设备支持"].append("系统诊断")
    else:
        print("   ⚠️ 系统诊断可能需要多设备支持")
        menus["系统诊断"]["建议"].append("添加多设备系统诊断")
    
    # 8. 模型服务页面分析
    print("\n🤖 模型服务页面")
    print("-" * 30)
    
    # 模型服务通常不直接依赖设备
    print("   ✅ 模型服务独立于设备")
    menus["模型服务"]["多设备支持"].append("设备无关")
    
    return menus

def generate_compatibility_report(menus):
    """生成兼容性报告"""
    print("\n" + "=" * 60)
    print("📊 多设备兼容性报告")
    print("=" * 60)
    
    total_issues = 0
    total_suggestions = 0
    
    for menu_name, menu_info in menus.items():
        print(f"\n📋 {menu_name}")
        print("-" * 30)
        
        if menu_info["多设备支持"]:
            print("✅ 已支持:")
            for feature in menu_info["多设备支持"]:
                print(f"   • {feature}")
        
        if menu_info["问题"]:
            print("❌ 问题:")
            for issue in menu_info["问题"]:
                print(f"   • {issue}")
            total_issues += len(menu_info["问题"])
        
        if menu_info["建议"]:
            print("💡 建议:")
            for suggestion in menu_info["建议"]:
                print(f"   • {suggestion}")
            total_suggestions += len(menu_info["建议"])
        
        if not menu_info["问题"] and not menu_info["建议"]:
            print("✅ 多设备兼容性良好")
    
    print(f"\n📈 总体统计:")
    print(f"   总问题数: {total_issues}")
    print(f"   总建议数: {total_suggestions}")
    print(f"   需要改进的菜单: {len([m for m in menus.values() if m['问题'] or m['建议']])}/8")
    
    return total_issues, total_suggestions

def generate_priority_fixes(menus):
    """生成优先修复建议"""
    print("\n" + "=" * 60)
    print("🎯 优先修复建议")
    print("=" * 60)
    
    high_priority = []
    medium_priority = []
    low_priority = []
    
    for menu_name, menu_info in menus.items():
        for issue in menu_info["问题"]:
            if "预览" in issue or "连接" in issue:
                high_priority.append(f"{menu_name}: {issue}")
            elif "任务" in issue or "安装" in issue:
                medium_priority.append(f"{menu_name}: {issue}")
            else:
                low_priority.append(f"{menu_name}: {issue}")
        
        for suggestion in menu_info["建议"]:
            if "批量" in suggestion or "预览" in suggestion:
                high_priority.append(f"{menu_name}: {suggestion}")
            elif "任务" in suggestion or "安装" in suggestion:
                medium_priority.append(f"{menu_name}: {suggestion}")
            else:
                low_priority.append(f"{menu_name}: {suggestion}")
    
    if high_priority:
        print("\n🔥 高优先级:")
        for i, item in enumerate(high_priority, 1):
            print(f"{i}. {item}")
    
    if medium_priority:
        print("\n⚠️ 中优先级:")
        for i, item in enumerate(medium_priority, 1):
            print(f"{i}. {item}")
    
    if low_priority:
        print("\n💡 低优先级:")
        for i, item in enumerate(low_priority, 1):
            print(f"{i}. {item}")
    
    return len(high_priority), len(medium_priority), len(low_priority)

def main():
    """主函数"""
    menus = analyze_all_menu_compatibility()
    total_issues, total_suggestions = generate_compatibility_report(menus)
    high, medium, low = generate_priority_fixes(menus)
    
    print(f"\n🎯 总结:")
    print(f"   高优先级问题: {high}")
    print(f"   中优先级问题: {medium}")
    print(f"   低优先级问题: {low}")
    print(f"   总体改进项: {total_issues + total_suggestions}")
    
    if total_issues == 0:
        print("\n🎉 所有关键问题已解决！")
        print("多设备兼容性基本满足需求。")
    else:
        print(f"\n⚠️ 还有 {total_issues} 个问题需要解决。")
        print("建议按优先级逐步改进多设备支持。")

if __name__ == "__main__":
    main()
