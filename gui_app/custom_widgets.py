# -*- coding: utf-8 -*-
"""
自定义UI组件
禁用鼠标滚动和上下箭头功能的SpinBox和ComboBox
"""

from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox, QComboBox
from PySide6.QtCore import Qt


class NoWheelSpinBox(QSpinBox):
    """禁用鼠标滚轮的SpinBox"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # 禁用鼠标滚轮
        self.setFocusPolicy(Qt.StrongFocus)
        # 禁用上下箭头按钮
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        # 设置只允许键盘输入
        self.setReadOnly(False)
        
    def wheelEvent(self, event):
        """完全忽略鼠标滚轮事件"""
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """禁用鼠标滚轮的DoubleSpinBox"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # 禁用鼠标滚轮
        self.setFocusPolicy(Qt.StrongFocus)
        # 禁用上下箭头按钮
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        # 设置只允许键盘输入
        self.setReadOnly(False)
        
    def wheelEvent(self, event):
        """完全忽略鼠标滚轮事件"""
        event.ignore()


class NoWheelComboBox(QComboBox):
    """禁用鼠标滚轮的ComboBox"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # 禁用鼠标滚轮
        self.setFocusPolicy(Qt.StrongFocus)
        
    def wheelEvent(self, event):
        """完全忽略鼠标滚轮事件"""
        event.ignore()
        
    def keyPressEvent(self, event):
        """只允许上下箭头键和回车键操作"""
        if event.key() in [Qt.Key_Up, Qt.Key_Down, Qt.Key_Enter, Qt.Key_Return, Qt.Key_F4]:
            super().keyPressEvent(event)
        else:
            event.ignore()


class NoWheelTimeEdit(QtWidgets.QTimeEdit):
    """禁用鼠标滚轮的TimeEdit"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # 禁用鼠标滚轮
        self.setFocusPolicy(Qt.StrongFocus)
        # 禁用上下箭头按钮
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        
    def wheelEvent(self, event):
        """完全忽略鼠标滚轮事件"""
        event.ignore()


def apply_no_wheel_style(widget):
    """应用无滚轮样式到组件"""
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        widget.setFocusPolicy(Qt.StrongFocus)
        widget.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
    elif isinstance(widget, QComboBox):
        widget.setFocusPolicy(Qt.StrongFocus)
    elif isinstance(widget, QtWidgets.QTimeEdit):
        widget.setFocusPolicy(Qt.StrongFocus)
        widget.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
