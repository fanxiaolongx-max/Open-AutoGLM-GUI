#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
鱼塘管理器 - GUI 启动入口

启动 Open-AutoGLM 的图形界面应用。
包含完整的日志系统、Qt平台设置和输入法支持。
"""

import os
import sys
import logging
import platform
from datetime import datetime
from pathlib import Path


def setup_logging():
    """设置完整的日志系统，同时输出到文件和控制台"""
    # 创建日志目录
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # 日志文件名包含日期
    log_file = log_dir / f"autoglm_{datetime.now().strftime('%Y%m%d')}.log"

    # 创建根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 文件处理器 - 记录所有级别
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)

    # 控制台处理器 - 只记录INFO及以上
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)

    # 添加处理器
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # 设置第三方库的日志级别
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    return log_file


def setup_qt_platform():
    """设置Qt平台相关的环境变量，避免Wayland警告"""
    # macOS 特定设置
    if platform.system() == 'Darwin':
        # 启用高 DPI 支持
        os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
        os.environ['QT_SCALE_FACTOR'] = '1.0'
        os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'
        os.environ['QT_FONT_DPI'] = '72'
        # 使用原生菜单栏
        os.environ['QT_MAC_WANTS_LAYER'] = '1'
        return

    # Linux/其他系统设置
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    xdg_session = os.environ.get("XDG_SESSION_TYPE", "")

    # 如果没有明确设置QT_QPA_PLATFORM，根据环境自动选择
    if not os.environ.get("QT_QPA_PLATFORM"):
        if wayland_display and xdg_session == "wayland":
            os.environ.setdefault("QT_QPA_PLATFORM", "wayland;xcb")
        else:
            os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    # 禁用Wayland的一些警告输出
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland.warning=false")


def setup_input_method():
    """设置Qt输入法环境变量以支持中文输入"""
    # 检查GTK输入法设置
    gtk_im = os.environ.get("GTK_IM_MODULE", "")
    xmodifiers = os.environ.get("XMODIFIERS", "")

    # fcitx5 在 Qt6 中应该使用 "fcitx" 作为 QT_IM_MODULE
    if "fcitx5" in xmodifiers or "fcitx5" in gtk_im or "fcitx" in xmodifiers or "fcitx" in gtk_im:
        os.environ["QT_IM_MODULE"] = "fcitx"
        os.environ["GTK_IM_MODULE"] = "fcitx"
        if not os.environ.get("XMODIFIERS"):
            os.environ["XMODIFIERS"] = "@im=fcitx"
    elif "ibus" in xmodifiers or "ibus" in gtk_im:
        os.environ["QT_IM_MODULE"] = "ibus"
        os.environ["GTK_IM_MODULE"] = "ibus"
        if not os.environ.get("XMODIFIERS"):
            os.environ["XMODIFIERS"] = "@im=ibus"
    else:
        os.environ.setdefault("QT_IM_MODULE", "fcitx")
        os.environ.setdefault("GTK_IM_MODULE", "fcitx")
        os.environ.setdefault("XMODIFIERS", "@im=fcitx")

    # 尝试设置 Qt 插件路径以加载系统的 fcitx 插件
    # Debian/Ubuntu 系统的 fcitx5-frontend-qt6 插件路径
    qt6_plugin_paths = [
        "/usr/lib/x86_64-linux-gnu/qt6/plugins",
        "/usr/lib64/qt6/plugins",
        "/usr/lib/qt6/plugins",
        "/usr/lib/x86_64-linux-gnu/qt6/plugins/platforminputcontexts",
    ]

    existing_plugin_path = os.environ.get("QT_PLUGIN_PATH", "")
    for path in qt6_plugin_paths:
        if os.path.exists(path) and path not in existing_plugin_path:
            if existing_plugin_path:
                existing_plugin_path = f"{path}:{existing_plugin_path}"
            else:
                existing_plugin_path = path

    if existing_plugin_path:
        os.environ["QT_PLUGIN_PATH"] = existing_plugin_path


def main():
    """主入口函数"""
    # 设置日志系统
    log_file = setup_logging()
    logger = logging.getLogger("AutoGLM")
    logger.info("=" * 60)
    logger.info("鱼塘管理器 GUI 启动")
    logger.info(f"日志文件: {log_file}")
    logger.info(f"Python版本: {sys.version}")
    logger.info(f"工作目录: {os.getcwd()}")
    logger.info(f"操作系统: {platform.system()} {platform.release()}")
    logger.info("=" * 60)

    # 设置Qt平台（必须在导入Qt之前）
    setup_qt_platform()

    # 设置输入法
    setup_input_method()

    try:
        # 加载字体
        try:
            from load_fonts import load_fonts
            load_fonts()
        except Exception as e:
            logger.warning(f"加载字体时出错: {e}")

        # 启动GUI
        from gui_app.app import run
        run()
    except Exception as e:
        logger.exception(f"程序异常退出: {e}")
        raise
    finally:
        logger.info("鱼塘管理器 GUI 退出")


if __name__ == "__main__":
    main()
