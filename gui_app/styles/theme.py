# -*- coding: utf-8 -*-
"""主题管理器 - 处理深色/浅色主题样式"""


def get_dark_stylesheet(base_font: int, title_font: int, card_title_font: int,
                        metric_font: int, small_font: int) -> str:
    """生成深色主题样式表"""
    return f"""
/* ═══════════════════════════════════════════════════════════════════
   Open AutoGLM - Premium UI Theme (Dark)
   Inspired by Linear, Vercel, Raycast, Arc Browser
═══════════════════════════════════════════════════════════════════ */

* {{
    font-family: 'Helvetica Neue', 'PingFang SC';
    font-size: {base_font}px;
    outline: none;
}}

/* Base Container */
QWidget {{
    background-color: #09090b;
    color: #fafafa;
}}

QMainWindow {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #09090b, stop:0.5 #0c0c0f, stop:1 #09090b);
}}

/* Navigation Sidebar */
QListWidget {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(24, 24, 27, 0.95), stop:1 rgba(18, 18, 20, 0.98));
    border: 1px solid rgba(63, 63, 70, 0.5);
    border-radius: 12px;
    padding: 6px 4px;
    margin: 6px;
}}

QListWidget::item {{
    color: #a1a1aa;
    padding: 10px 14px;
    margin: 2px 4px;
    border-radius: 8px;
    border: 1px solid transparent;
}}

QListWidget::item:hover {{
    background: rgba(63, 63, 70, 0.4);
    color: #e4e4e7;
    border: 1px solid rgba(82, 82, 91, 0.3);
}}

QListWidget::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99, 102, 241, 0.9), stop:1 rgba(139, 92, 246, 0.9));
    color: #ffffff;
    font-weight: 600;
    border: 1px solid rgba(167, 139, 250, 0.5);
}}

/* Cards & Panels */
QFrame {{
    background: transparent;
}}

QFrame#card {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(24, 24, 27, 0.9), stop:1 rgba(18, 18, 20, 0.95));
    border: 1px solid rgba(63, 63, 70, 0.4);
    border-radius: 12px;
    padding: 16px;
}}

QFrame#card:hover {{
    border: 1px solid rgba(99, 102, 241, 0.3);
}}

/* Typography */
QLabel {{
    color: #e4e4e7;
    background: transparent;
}}

QLabel#title {{
    font-size: {title_font}px;
    font-weight: 700;
    color: #fafafa;
    padding: 6px 0 12px 0;
    letter-spacing: -0.5px;
}}

QLabel#subtitle {{
    font-size: 14px;
    font-weight: 400;
    color: #a1a1aa;
    letter-spacing: 0.2px;
}}

QLabel#cardTitle {{
    font-size: {card_title_font}px;
    font-weight: 600;
    color: #f4f4f5;
    padding-bottom: 6px;
    letter-spacing: -0.2px;
}}

QLabel#metricValue {{
    font-size: {metric_font}px;
    font-weight: 700;
    color: #a78bfa;
    letter-spacing: -1px;
}}

QLabel#metricLabel {{
    font-size: {small_font}px;
    font-weight: 500;
    color: #71717a;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* Buttons */
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #6366f1, stop:1 #8b5cf6);
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    color: #ffffff;
    font-weight: 600;
    font-size: {base_font}px;
    min-height: 18px;
}}

QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #818cf8, stop:1 #a78bfa);
}}

QPushButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #4f46e5, stop:1 #7c3aed);
}}

QPushButton:disabled {{
    background: rgba(39, 39, 42, 0.8);
    color: #52525b;
    border: 1px solid rgba(63, 63, 70, 0.3);
}}

QPushButton#secondary {{
    background: rgba(39, 39, 42, 0.6);
    border: 1px solid rgba(63, 63, 70, 0.5);
    color: #a1a1aa;
}}

QPushButton#secondary:hover {{
    background: rgba(63, 63, 70, 0.6);
    border: 1px solid rgba(82, 82, 91, 0.6);
    color: #e4e4e7;
}}

QPushButton#success {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #10b981, stop:1 #059669);
}}

QPushButton#success:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #34d399, stop:1 #10b981);
}}

QPushButton#danger {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #ef4444, stop:1 #dc2626);
}}

QPushButton#danger:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #f87171, stop:1 #ef4444);
}}

/* Input Fields */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: rgba(24, 24, 27, 0.8);
    border: 1px solid rgba(63, 63, 70, 0.5);
    border-radius: 8px;
    padding: 8px 12px;
    color: #fafafa;
    min-height: 18px;
    min-width: 200px;
    selection-background-color: rgba(99, 102, 241, 0.5);
}}

QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border: 1px solid rgba(82, 82, 91, 0.7);
    background: rgba(30, 30, 33, 0.9);
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid rgba(99, 102, 241, 0.7);
    background: rgba(24, 24, 27, 1);
}}

QLineEdit::placeholder {{
    color: #52525b;
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #71717a;
    margin-right: 10px;
}}

QComboBox QAbstractItemView {{
    background: rgba(24, 24, 27, 0.98);
    border: 1px solid rgba(63, 63, 70, 0.5);
    border-radius: 8px;
    padding: 4px;
    selection-background-color: rgba(99, 102, 241, 0.5);
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px;
    height: 0px;
    border: none;
    background: none;
}}

QSpinBox::up-arrow, QSpinBox::down-arrow,
QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{
    width: 0px;
    height: 0px;
    border: none;
    background: none;
}}

QTimeEdit, QDateTimeEdit {{
    background: rgba(24, 24, 27, 0.8);
    border: 1px solid rgba(63, 63, 70, 0.5);
    border-radius: 8px;
    padding: 8px 12px;
    color: #fafafa;
    min-height: 18px;
    selection-background-color: rgba(99, 102, 241, 0.5);
}}

QTimeEdit:hover, QDateTimeEdit:hover {{
    border: 1px solid rgba(82, 82, 91, 0.7);
    background: rgba(30, 30, 33, 0.9);
}}

QTimeEdit:focus, QDateTimeEdit:focus {{
    border: 1px solid rgba(99, 102, 241, 0.7);
    background: rgba(24, 24, 27, 1);
}}

QTimeEdit::up-button, QTimeEdit::down-button,
QDateTimeEdit::up-button, QDateTimeEdit::down-button {{
    background: transparent;
    border: none;
    width: 20px;
    subcontrol-origin: border;
}}

QTimeEdit::up-button, QDateTimeEdit::up-button {{
    subcontrol-position: top right;
}}

QTimeEdit::down-button, QDateTimeEdit::down-button {{
    subcontrol-position: bottom right;
}}

QTimeEdit::up-arrow, QDateTimeEdit::up-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #71717a;
    width: 0;
    height: 0;
}}

QTimeEdit::down-arrow, QDateTimeEdit::down-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #71717a;
    width: 0;
    height: 0;
}}

QTimeEdit::up-arrow:hover, QDateTimeEdit::up-arrow:hover,
QTimeEdit::down-arrow:hover, QDateTimeEdit::down-arrow:hover {{
    border-bottom-color: #a78bfa;
    border-top-color: #a78bfa;
}}

/* Text Areas */
QPlainTextEdit, QTextEdit {{
    background: rgba(18, 18, 20, 0.95);
    border: 1px solid rgba(63, 63, 70, 0.4);
    border-radius: 10px;
    padding: 10px;
    color: #e4e4e7;
    font-family: 'Menlo', 'Monaco';
    font-size: {base_font}px;
    line-height: 1.5;
    selection-background-color: rgba(99, 102, 241, 0.4);
}}

QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid rgba(99, 102, 241, 0.5);
}}

/* Splitter */
QSplitter::handle {{
    background: rgba(63, 63, 70, 0.3);
    width: 2px;
    margin: 0 6px;
    border-radius: 1px;
}}

QSplitter::handle:hover {{
    background: rgba(99, 102, 241, 0.6);
}}

/* Timeline List */
QListWidget#timeline_list {{
    background: rgba(18, 18, 20, 0.6);
    border: 1px solid rgba(63, 63, 70, 0.3);
    border-radius: 10px;
    padding: 6px;
}}

QListWidget#timeline_list::item {{
    padding: 8px 12px;
    margin: 2px 0;
    border-radius: 6px;
    border: none;
    color: #a1a1aa;
    font-size: {small_font}px;
}}

QListWidget#timeline_list::item:hover {{
    background: rgba(63, 63, 70, 0.3);
    color: #e4e4e7;
}}

/* Scrollbars */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 4px 2px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background: rgba(82, 82, 91, 0.5);
    border-radius: 3px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: rgba(99, 102, 241, 0.6);
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 2px 4px;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal {{
    background: rgba(82, 82, 91, 0.5);
    border-radius: 3px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background: rgba(99, 102, 241, 0.6);
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* Message Boxes & Tooltips */
QMessageBox {{
    background: rgba(24, 24, 27, 0.98);
}}

QMessageBox QLabel {{
    color: #e4e4e7;
}}

QToolTip {{
    background: rgba(24, 24, 27, 0.95);
    border: 1px solid rgba(63, 63, 70, 0.5);
    border-radius: 6px;
    padding: 6px 10px;
    color: #e4e4e7;
    font-size: {small_font}px;
}}

/* Form Labels */
QFormLayout QLabel {{
    font-weight: 500;
    color: #a1a1aa;
    padding-right: 10px;
}}

/* Status Indicators */
QLabel#status_ok {{
    color: #10b981;
    font-weight: 600;
}}

QLabel#status_error {{
    color: #ef4444;
    font-weight: 600;
}}

QLabel#status_warning {{
    color: #f59e0b;
    font-weight: 600;
}}

QLabel#status_info {{
    color: #6366f1;
    font-weight: 600;
}}

/* Preview Area */
QLabel#preview {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #18181b, stop:1 #09090b);
    border: 2px solid rgba(63, 63, 70, 0.5);
    border-radius: 16px;
}}

/* Tree Widget */
QTreeWidget {{
    background: rgba(18, 18, 20, 0.95);
    border: 1px solid rgba(63, 63, 70, 0.4);
    border-radius: 8px;
    padding: 4px;
    color: #e4e4e7;
    selection-background-color: rgba(99, 102, 241, 0.5);
}}

QTreeWidget::item {{
    padding: 6px 8px;
    border-radius: 4px;
    color: #e4e4e7;
}}

QTreeWidget::item:hover {{
    background: rgba(63, 63, 70, 0.4);
}}

QTreeWidget::item:selected {{
    background: rgba(99, 102, 241, 0.6);
    color: #ffffff;
}}

QTreeWidget::item:alternate {{
    background: rgba(24, 24, 27, 0.5);
}}

QHeaderView::section {{
    background: rgba(24, 24, 27, 0.9);
    color: #a1a1aa;
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid rgba(63, 63, 70, 0.5);
    font-weight: 600;
}}

QHeaderView::section:hover {{
    background: rgba(39, 39, 42, 0.9);
    color: #e4e4e7;
}}

/* Context Menu */
QMenu {{
    background: rgba(24, 24, 27, 0.98);
    border: 1px solid rgba(63, 63, 70, 0.5);
    border-radius: 8px;
    padding: 6px;
    color: #e4e4e7;
}}

QMenu::item {{
    padding: 8px 24px 8px 12px;
    border-radius: 4px;
    color: #e4e4e7;
}}

QMenu::item:selected {{
    background: rgba(99, 102, 241, 0.6);
    color: #ffffff;
}}

QMenu::item:disabled {{
    color: #52525b;
}}

QMenu::separator {{
    height: 1px;
    background: rgba(63, 63, 70, 0.5);
    margin: 4px 8px;
}}

/* Dialog Boxes */
QDialog {{
    background: rgba(24, 24, 27, 0.98);
    color: #e4e4e7;
}}

QInputDialog {{
    background: rgba(24, 24, 27, 0.98);
    color: #e4e4e7;
}}

QFileDialog {{
    background: rgba(24, 24, 27, 0.98);
    color: #e4e4e7;
}}

QFileDialog QTreeView {{
    background: rgba(18, 18, 20, 0.95);
    color: #e4e4e7;
    border: 1px solid rgba(63, 63, 70, 0.4);
    border-radius: 6px;
}}

QFileDialog QListView {{
    background: rgba(18, 18, 20, 0.95);
    color: #e4e4e7;
    border: 1px solid rgba(63, 63, 70, 0.4);
    border-radius: 6px;
}}

/* Checkbox */
QCheckBox {{
    color: #e4e4e7;
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid rgba(63, 63, 70, 0.6);
    background: rgba(24, 24, 27, 0.8);
}}

QCheckBox::indicator:hover {{
    border: 1px solid rgba(99, 102, 241, 0.6);
    background: rgba(39, 39, 42, 0.8);
}}

QCheckBox::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #6366f1, stop:1 #8b5cf6);
    border: 1px solid rgba(99, 102, 241, 0.8);
}}
"""


def get_light_stylesheet(base_font: int, title_font: int, card_title_font: int,
                         metric_font: int, small_font: int) -> str:
    """生成浅色主题样式表"""
    return f"""
/* ═══════════════════════════════════════════════════════════════════
   Open AutoGLM - Light Theme
   Clean and modern light mode
═══════════════════════════════════════════════════════════════════ */

* {{
    font-family: 'Helvetica Neue', 'PingFang SC';
    font-size: {base_font}px;
    outline: none;
}}

/* Base Container */
QWidget {{
    background-color: #f4f4f5;
    color: #18181b;
}}

QMainWindow {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #f4f4f5, stop:0.5 #fafafa, stop:1 #f4f4f5);
}}

/* Navigation Sidebar */
QListWidget {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.95), stop:1 rgba(244, 244, 245, 0.98));
    border: 1px solid rgba(228, 228, 231, 0.8);
    border-radius: 12px;
    padding: 6px 4px;
    margin: 6px;
}}

QListWidget::item {{
    color: #52525b;
    padding: 10px 14px;
    margin: 2px 4px;
    border-radius: 8px;
    border: 1px solid transparent;
}}

QListWidget::item:hover {{
    background: rgba(228, 228, 231, 0.6);
    color: #18181b;
    border: 1px solid rgba(212, 212, 216, 0.5);
}}

QListWidget::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99, 102, 241, 0.9), stop:1 rgba(139, 92, 246, 0.9));
    color: #ffffff;
    font-weight: 600;
    border: 1px solid rgba(167, 139, 250, 0.5);
}}

/* Cards & Panels */
QFrame {{
    background: transparent;
}}

QFrame#card {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.95), stop:1 rgba(250, 250, 250, 0.98));
    border: 1px solid rgba(228, 228, 231, 0.6);
    border-radius: 12px;
    padding: 16px;
}}

QFrame#card:hover {{
    border: 1px solid rgba(99, 102, 241, 0.4);
}}

/* Typography */
QLabel {{
    color: #3f3f46;
    background: transparent;
}}

QLabel#title {{
    font-size: {title_font}px;
    font-weight: 700;
    color: #18181b;
    padding: 6px 0 12px 0;
    letter-spacing: -0.5px;
}}

QLabel#subtitle {{
    font-size: 14px;
    font-weight: 400;
    color: #71717a;
    letter-spacing: 0.2px;
}}

QLabel#cardTitle {{
    font-size: {card_title_font}px;
    font-weight: 600;
    color: #27272a;
    padding-bottom: 6px;
    letter-spacing: -0.2px;
}}

QLabel#metricValue {{
    font-size: {metric_font}px;
    font-weight: 700;
    color: #7c3aed;
    letter-spacing: -1px;
}}

QLabel#metricLabel {{
    font-size: {small_font}px;
    font-weight: 500;
    color: #71717a;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* Buttons */
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #6366f1, stop:1 #8b5cf6);
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    color: #ffffff;
    font-weight: 600;
    font-size: {base_font}px;
    min-height: 18px;
}}

QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #818cf8, stop:1 #a78bfa);
}}

QPushButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #4f46e5, stop:1 #7c3aed);
}}

QPushButton:disabled {{
    background: rgba(228, 228, 231, 0.8);
    color: #a1a1aa;
    border: 1px solid rgba(212, 212, 216, 0.5);
}}

QPushButton#secondary {{
    background: rgba(255, 255, 255, 0.8);
    border: 1px solid rgba(212, 212, 216, 0.8);
    color: #52525b;
}}

QPushButton#secondary:hover {{
    background: rgba(244, 244, 245, 0.9);
    border: 1px solid rgba(161, 161, 170, 0.6);
    color: #18181b;
}}

QPushButton#success {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #10b981, stop:1 #059669);
}}

QPushButton#success:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #34d399, stop:1 #10b981);
}}

QPushButton#danger {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #ef4444, stop:1 #dc2626);
}}

QPushButton#danger:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #f87171, stop:1 #ef4444);
}}

/* Input Fields */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid rgba(212, 212, 216, 0.8);
    border-radius: 8px;
    padding: 8px 12px;
    color: #18181b;
    min-height: 18px;
    min-width: 200px;
    selection-background-color: rgba(99, 102, 241, 0.3);
}}

QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border: 1px solid rgba(161, 161, 170, 0.8);
    background: rgba(255, 255, 255, 1);
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid rgba(99, 102, 241, 0.7);
    background: rgba(255, 255, 255, 1);
}}

QLineEdit::placeholder {{
    color: #a1a1aa;
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #71717a;
    margin-right: 10px;
}}

QComboBox QAbstractItemView {{
    background: rgba(255, 255, 255, 0.98);
    border: 1px solid rgba(212, 212, 216, 0.8);
    border-radius: 8px;
    padding: 4px;
    selection-background-color: rgba(99, 102, 241, 0.3);
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px;
    height: 0px;
    border: none;
    background: none;
}}

QSpinBox::up-arrow, QSpinBox::down-arrow,
QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{
    width: 0px;
    height: 0px;
    border: none;
    background: none;
}}

QTimeEdit, QDateTimeEdit {{
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid rgba(212, 212, 216, 0.8);
    border-radius: 8px;
    padding: 8px 12px;
    color: #18181b;
    min-height: 18px;
    selection-background-color: rgba(99, 102, 241, 0.3);
}}

QTimeEdit:hover, QDateTimeEdit:hover {{
    border: 1px solid rgba(161, 161, 170, 0.8);
    background: rgba(255, 255, 255, 1);
}}

QTimeEdit:focus, QDateTimeEdit:focus {{
    border: 1px solid rgba(99, 102, 241, 0.7);
    background: rgba(255, 255, 255, 1);
}}

QTimeEdit::up-button, QTimeEdit::down-button,
QDateTimeEdit::up-button, QDateTimeEdit::down-button {{
    background: transparent;
    border: none;
    width: 20px;
    subcontrol-origin: border;
}}

QTimeEdit::up-button, QDateTimeEdit::up-button {{
    subcontrol-position: top right;
}}

QTimeEdit::down-button, QDateTimeEdit::down-button {{
    subcontrol-position: bottom right;
}}

QTimeEdit::up-arrow, QDateTimeEdit::up-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #71717a;
    width: 0;
    height: 0;
}}

QTimeEdit::down-arrow, QDateTimeEdit::down-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #71717a;
    width: 0;
    height: 0;
}}

QTimeEdit::up-arrow:hover, QDateTimeEdit::up-arrow:hover,
QTimeEdit::down-arrow:hover, QDateTimeEdit::down-arrow:hover {{
    border-bottom-color: #7c3aed;
    border-top-color: #7c3aed;
}}

/* Text Areas */
QPlainTextEdit, QTextEdit {{
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(212, 212, 216, 0.6);
    border-radius: 10px;
    padding: 10px;
    color: #27272a;
    font-family: 'Menlo', 'Monaco';
    font-size: {base_font}px;
    line-height: 1.5;
    selection-background-color: rgba(99, 102, 241, 0.3);
}}

QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid rgba(99, 102, 241, 0.5);
}}

/* Splitter */
QSplitter::handle {{
    background: rgba(212, 212, 216, 0.5);
    width: 2px;
    margin: 0 6px;
    border-radius: 1px;
}}

QSplitter::handle:hover {{
    background: rgba(99, 102, 241, 0.6);
}}

/* Timeline List */
QListWidget#timeline_list {{
    background: rgba(255, 255, 255, 0.8);
    border: 1px solid rgba(212, 212, 216, 0.5);
    border-radius: 10px;
    padding: 6px;
}}

QListWidget#timeline_list::item {{
    padding: 8px 12px;
    margin: 2px 0;
    border-radius: 6px;
    border: none;
    color: #52525b;
    font-size: {small_font}px;
}}

QListWidget#timeline_list::item:hover {{
    background: rgba(228, 228, 231, 0.5);
    color: #18181b;
}}

/* Scrollbars */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 4px 2px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background: rgba(161, 161, 170, 0.5);
    border-radius: 3px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: rgba(99, 102, 241, 0.6);
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 2px 4px;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal {{
    background: rgba(161, 161, 170, 0.5);
    border-radius: 3px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background: rgba(99, 102, 241, 0.6);
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* Message Boxes & Tooltips */
QMessageBox {{
    background: rgba(255, 255, 255, 0.98);
}}

QMessageBox QLabel {{
    color: #27272a;
}}

QToolTip {{
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(212, 212, 216, 0.8);
    border-radius: 6px;
    padding: 6px 10px;
    color: #27272a;
    font-size: {small_font}px;
}}

/* Form Labels */
QFormLayout QLabel {{
    font-weight: 500;
    color: #52525b;
    padding-right: 10px;
}}

/* Status Indicators */
QLabel#status_ok {{
    color: #059669;
    font-weight: 600;
}}

QLabel#status_error {{
    color: #dc2626;
    font-weight: 600;
}}

QLabel#status_warning {{
    color: #d97706;
    font-weight: 600;
}}

QLabel#status_info {{
    color: #4f46e5;
    font-weight: 600;
}}

/* Preview Area */
QLabel#preview {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #e4e4e7, stop:1 #d4d4d8);
    border: 2px solid rgba(161, 161, 170, 0.5);
    border-radius: 16px;
}}

/* Tree Widget */
QTreeWidget {{
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(212, 212, 216, 0.6);
    border-radius: 8px;
    padding: 4px;
    color: #27272a;
    selection-background-color: rgba(99, 102, 241, 0.3);
}}

QTreeWidget::item {{
    padding: 6px 8px;
    border-radius: 4px;
    color: #27272a;
}}

QTreeWidget::item:hover {{
    background: rgba(228, 228, 231, 0.6);
}}

QTreeWidget::item:selected {{
    background: rgba(99, 102, 241, 0.5);
    color: #ffffff;
}}

QTreeWidget::item:alternate {{
    background: rgba(244, 244, 245, 0.5);
}}

QHeaderView::section {{
    background: rgba(250, 250, 250, 0.95);
    color: #52525b;
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid rgba(212, 212, 216, 0.6);
    font-weight: 600;
}}

QHeaderView::section:hover {{
    background: rgba(244, 244, 245, 0.95);
    color: #18181b;
}}

/* Context Menu */
QMenu {{
    background: rgba(255, 255, 255, 0.98);
    border: 1px solid rgba(212, 212, 216, 0.8);
    border-radius: 8px;
    padding: 6px;
    color: #27272a;
}}

QMenu::item {{
    padding: 8px 24px 8px 12px;
    border-radius: 4px;
    color: #27272a;
}}

QMenu::item:selected {{
    background: rgba(99, 102, 241, 0.5);
    color: #ffffff;
}}

QMenu::item:disabled {{
    color: #a1a1aa;
}}

QMenu::separator {{
    height: 1px;
    background: rgba(212, 212, 216, 0.6);
    margin: 4px 8px;
}}

/* Dialog Boxes */
QDialog {{
    background: rgba(255, 255, 255, 0.98);
    color: #27272a;
}}

QInputDialog {{
    background: rgba(255, 255, 255, 0.98);
    color: #27272a;
}}

QFileDialog {{
    background: rgba(255, 255, 255, 0.98);
    color: #27272a;
}}

QFileDialog QTreeView {{
    background: rgba(255, 255, 255, 0.95);
    color: #27272a;
    border: 1px solid rgba(212, 212, 216, 0.6);
    border-radius: 6px;
}}

QFileDialog QListView {{
    background: rgba(255, 255, 255, 0.95);
    color: #27272a;
    border: 1px solid rgba(212, 212, 216, 0.6);
    border-radius: 6px;
}}

/* Checkbox */
QCheckBox {{
    color: #27272a;
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid rgba(212, 212, 216, 0.8);
    background: rgba(255, 255, 255, 0.9);
}}

QCheckBox::indicator:hover {{
    border: 1px solid rgba(99, 102, 241, 0.6);
    background: rgba(244, 244, 245, 0.9);
}}

QCheckBox::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #6366f1, stop:1 #8b5cf6);
    border: 1px solid rgba(99, 102, 241, 0.8);
}}
"""


class ThemeManager:
    """主题管理器"""

    def __init__(self, font_scale: float = 1.0):
        self.font_scale = font_scale
        self.current_theme = 'dark'

    def get_font_sizes(self) -> tuple[int, int, int, int, int]:
        """获取缩放后的字体大小"""
        base_font = int(12 * self.font_scale)
        title_font = int(20 * self.font_scale)
        card_title_font = int(14 * self.font_scale)
        metric_font = int(24 * self.font_scale)
        small_font = int(11 * self.font_scale)
        return base_font, title_font, card_title_font, metric_font, small_font

    def get_stylesheet(self, theme: str = None) -> str:
        """获取指定主题的样式表"""
        if theme is None:
            theme = self.current_theme

        base_font, title_font, card_title_font, metric_font, small_font = self.get_font_sizes()

        if theme == 'light':
            return get_light_stylesheet(base_font, title_font, card_title_font, metric_font, small_font)
        else:
            return get_dark_stylesheet(base_font, title_font, card_title_font, metric_font, small_font)

    def set_theme(self, theme: str):
        """设置当前主题"""
        self.current_theme = theme

    def set_font_scale(self, scale: float):
        """设置字体缩放"""
        self.font_scale = scale
