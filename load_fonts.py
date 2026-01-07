# -*- coding: utf-8 -*-
"""
字体加载工具
处理跨平台的字体加载和设置
"""

import os
import platform
from pathlib import Path
from typing import List, Optional

from PySide6 import QtWidgets, QtGui, QtCore


def get_system_fonts_dirs() -> List[Path]:
    """获取系统字体目录"""
    system = platform.system()
    font_dirs = []
    
    if system == "Darwin":  # macOS
        font_dirs.extend([
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library" / "Fonts"
        ])
    elif system == "Windows":
        font_dirs.extend([
            Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"
        ])
    else:  # Linux and others
        font_dirs.extend([
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".local" / "share" / "fonts",
            Path.home() / ".fonts"
        ])
    
    # 添加项目字体目录
    font_dirs.insert(0, Path(__file__).parent / "fonts")
    
    # 过滤掉不存在的目录
    return [d for d in font_dirs if d.exists()]


def load_fonts():
    """
    加载应用程序字体
    
    1. 加载系统字体
    2. 加载项目字体
    3. 设置默认字体
    """
    app = QtWidgets.QApplication.instance()
    if not app:
        return
    
    # 获取所有字体目录
    font_dirs = get_system_fonts_dirs()
    
    # 支持的字体格式
    font_extensions = ['.ttf', '.otf', '.ttc', '.pcf', '.pfa', '.pfb']
    
    # 加载字体
    loaded_fonts = set()
    for font_dir in font_dirs:
        try:
            for ext in font_extensions:
                for font_file in font_dir.rglob(f"*{ext}"):
                    try:
                        font_id = QtGui.QFontDatabase.addApplicationFont(str(font_file))
                        if font_id != -1:
                            font_family = QtGui.QFontDatabase.applicationFontFamilies(font_id)[0]
                            loaded_fonts.add(font_family)
                    except Exception as e:
                        print(f"加载字体 {font_file} 失败: {e}")
        except Exception as e:
            print(f"扫描字体目录 {font_dir} 失败: {e}")
    
    # 设置默认字体
    set_default_font(loaded_fonts)


def set_default_font(available_fonts: set = None):
    """设置应用程序默认字体"""
    app = QtWidgets.QApplication.instance()
    if not app:
        return
    
    # 获取系统字体数据库
    font_db = QtGui.QFontDatabase()
    
    # 首选字体列表（按优先级排序）
    preferred_fonts = {
        'zh_CN': [
            'PingFang SC',       # macOS 中文
            'Microsoft YaHei',   # Windows 中文
            'Noto Sans CJK SC',  # Linux 中文
            'Source Han Sans SC', # 思源黑体
            'WenQuanYi Micro Hei', # 文泉驿微米黑
        ],
        'default': [
            'Segoe UI',          # Windows
            'Helvetica Neue',    # macOS
            'Arial',             # 通用
            'sans-serif'         # 最后的后备
        ]
    }
    
    # 获取系统语言环境
    locale = QtCore.QLocale()
    lang = locale.name()  # 例如: 'zh_CN', 'en_US'
    
    # 合并字体列表
    font_candidates = preferred_fonts.get(lang, []) + preferred_fonts['default']
    
    # 获取可用的字体
    if available_fonts is None:
        available_fonts = set(font_db.families())
    
    # 查找第一个可用的字体
    selected_font = None
    for font in font_candidates:
        if font in available_fonts:
            selected_font = font
            break
    
    # 设置应用程序字体
    if selected_font:
        font = app.font()
        font.setFamily(selected_font)
        
        # 根据系统设置合适的字体大小
        if platform.system() == 'Darwin':
            font.setPointSize(13)  # macOS 默认字体稍大
        else:
            font.setPointSize(9)   # 其他系统默认大小
            
        app.setFont(font)
        print(f"设置默认字体: {selected_font}")
    else:
        print("警告: 未找到合适的字体，使用系统默认字体")


if __name__ == "__main__":
    # 测试字体加载
    import sys
    app = QtWidgets.QApplication(sys.argv)
    load_fonts()
    
    # 显示已加载的字体
    font_db = QtGui.QFontDatabase()
    print("\n已加载字体:")
    for family in sorted(font_db.families()):
        print(f"- {family}")
    
    # 显示当前字体信息
    current_font = app.font()
    print(f"\n当前字体: {current_font.family()}, 大小: {current_font.pointSize()}")
    
    sys.exit()
