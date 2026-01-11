# -*- coding: utf-8 -*-
"""通用 UI 组件 - 自定义控件和对话框"""

from PySide6 import QtCore, QtGui, QtWidgets


class CustomTitleBar(QtWidgets.QWidget):
    """自定义标题栏，支持无边框窗口拖动"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self._drag_pos = None
        self._is_maximized = False

        self.setFixedHeight(38)
        self.setMouseTracking(True)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        # 窗口控制按钮（macOS 风格，左侧小圆钮）
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(8)

        self.close_btn = QtWidgets.QPushButton("×")
        self.close_btn.setFixedSize(12, 12)
        self.close_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self._close_window)
        self.close_btn.setToolTip("关闭")

        self.minimize_btn = QtWidgets.QPushButton("−")
        self.minimize_btn.setFixedSize(12, 12)
        self.minimize_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.minimize_btn.clicked.connect(self._minimize_window)
        self.minimize_btn.setToolTip("最小化")

        self.maximize_btn = QtWidgets.QPushButton("□")
        self.maximize_btn.setFixedSize(12, 12)
        self.maximize_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.maximize_btn.clicked.connect(self._toggle_maximize)
        self.maximize_btn.setToolTip("最大化")

        btn_layout.addWidget(self.close_btn)
        btn_layout.addWidget(self.minimize_btn)
        btn_layout.addWidget(self.maximize_btn)

        # 标题
        self.title_label = QtWidgets.QLabel("鱼塘管理器")
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)

        layout.addLayout(btn_layout)
        layout.addWidget(self.title_label, 1)
        layout.addSpacing(60)  # 平衡左侧按钮的空间

        self._apply_style()

    def _apply_style(self):
        """应用样式"""
        is_light = False
        if self.parent_window and hasattr(self.parent_window, 'current_theme'):
            is_light = self.parent_window.current_theme == 'light'

        if is_light:
            bg_color = "rgba(244, 244, 245, 0.95)"
            title_color = "#18181b"
            border_color = "rgba(212, 212, 216, 0.5)"
        else:
            bg_color = "rgba(24, 24, 27, 0.95)"
            title_color = "#e4e4e7"
            border_color = "rgba(63, 63, 70, 0.5)"

        self.setStyleSheet(f"""
            CustomTitleBar {{
                background: {bg_color};
                border-bottom: 1px solid {border_color};
            }}
            QLabel {{
                color: {title_color};
                font-size: 13px;
                font-weight: 500;
                background: transparent;
            }}
            QPushButton {{
                border-radius: 7px;
                border: none;
            }}
        """)

        # macOS 风格的窗口按钮颜色（小圆钮带图标）
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: #ff5f57;
                border-radius: 6px;
                color: transparent;
                font-size: 10px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                background: #ff3b30;
                color: #4a0000;
            }
        """)
        self.minimize_btn.setStyleSheet("""
            QPushButton {
                background: #ffbd2e;
                border-radius: 6px;
                color: transparent;
                font-size: 10px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                background: #ff9500;
                color: #4a3000;
            }
        """)
        self.maximize_btn.setStyleSheet("""
            QPushButton {
                background: #28c840;
                border-radius: 6px;
                color: transparent;
                font-size: 8px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                background: #34c759;
                color: #004a00;
            }
        """)

    def update_theme(self):
        """更新主题"""
        self._apply_style()

    def _close_window(self):
        if self.parent_window:
            self.parent_window.close()

    def _minimize_window(self):
        if self.parent_window:
            self.parent_window.showMinimized()

    def _toggle_maximize(self):
        if self.parent_window:
            if self._is_maximized:
                self.parent_window.showNormal()
                self._is_maximized = False
            else:
                self.parent_window.showMaximized()
                self._is_maximized = True

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.parent_window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton and self._drag_pos is not None:
            # 如果最大化状态，先恢复正常
            if self._is_maximized:
                self.parent_window.showNormal()
                self._is_maximized = False
                # 调整拖动位置到窗口中心
                self._drag_pos = QtCore.QPoint(self.parent_window.width() // 2, 20)
            self.parent_window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._toggle_maximize()
            event.accept()


class HoverExpandCard(QtWidgets.QFrame):
    """鼠标悬停时自动展开的卡片控件"""

    def __init__(self, collapsed_stretch=2, expanded_stretch=4, parent=None):
        super().__init__(parent)
        self.collapsed_stretch = collapsed_stretch
        self.expanded_stretch = expanded_stretch
        self.setObjectName("card")
        self._animation = None

    def enterEvent(self, event):
        """鼠标进入时展开"""
        super().enterEvent(event)
        self._animate_stretch(self.expanded_stretch)

    def leaveEvent(self, event):
        """鼠标离开时收缩"""
        super().leaveEvent(event)
        self._animate_stretch(self.collapsed_stretch)

    def _animate_stretch(self, target_stretch):
        """动画改变 stretch 因子"""
        parent_layout = self.parentWidget().layout() if self.parentWidget() else None
        if parent_layout and isinstance(parent_layout, QtWidgets.QBoxLayout):
            index = parent_layout.indexOf(self)
            if index >= 0:
                parent_layout.setStretch(index, target_stretch)


class DragDropTextEdit(QtWidgets.QPlainTextEdit):
    """支持拖拽文件导入的文本编辑框"""
    fileImported = QtCore.Signal(str)  # 导入的文件路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drag_hover = False

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile().lower()
                # 支持常见文本文件格式
                if file_path.endswith(('.txt', '.md', '.json', '.yaml', '.yml', '.py', '.sh')):
                    event.acceptProposedAction()
                    self._drag_hover = True
                    self._update_drag_style()
                    return
        # 允许正常的文本拖拽
        if event.mimeData().hasText():
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._drag_hover = False
        self._update_drag_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._drag_hover = False
        self._update_drag_style()

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.setPlainText(content)
                    self.fileImported.emit(file_path)
                    event.acceptProposedAction()
                    return
                except Exception:
                    pass

        # 允许正常的文本拖拽
        if event.mimeData().hasText():
            super().dropEvent(event)
            return

        event.ignore()

    def _update_drag_style(self):
        if self._drag_hover:
            self.setStyleSheet(
                """
                QPlainTextEdit {
                    background: rgba(99, 102, 241, 0.1);
                    border: 2px dashed rgba(99, 102, 241, 0.8);
                    border-radius: 8px;
                }
                """
            )
        else:
            self.setStyleSheet("")


class DropZoneWidget(QtWidgets.QLabel):
    fileDropped = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self._is_light_theme = False
        self._update_style(False)

    def _update_style(self, hover):
        is_light = getattr(self, '_is_light_theme', False)
        if hover:
            self.setStyleSheet(
                """
                QLabel {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(99, 102, 241, 0.15), stop:1 rgba(139, 92, 246, 0.15));
                    border: 2px dashed rgba(99, 102, 241, 0.8);
                    border-radius: 16px;
                    color: #a78bfa;
                    font-size: 16px;
                    font-weight: 600;
                    padding: 40px;
                }
                """
            )
        else:
            if is_light:
                self.setStyleSheet(
                    """
                    QLabel {
                        background: rgba(244, 244, 245, 0.8);
                        border: 2px dashed rgba(161, 161, 170, 0.6);
                        border-radius: 16px;
                        color: #52525b;
                        font-size: 16px;
                        font-weight: 500;
                        padding: 40px;
                    }
                    """
                )
            else:
                self.setStyleSheet(
                    """
                    QLabel {
                        background: rgba(24, 24, 27, 0.6);
                        border: 2px dashed rgba(63, 63, 70, 0.6);
                        border-radius: 16px;
                        color: #71717a;
                        font-size: 16px;
                        font-weight: 500;
                        padding: 40px;
                    }
                    """
                )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith('.apk'):
                event.acceptProposedAction()
                self._update_style(True)
                self.setText("📦 松开以安装APK")
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._update_style(False)
        self.setText("📱 拖拽APK文件到此处安装\n\n支持 .apk 格式")

    def dropEvent(self, event):
        self._update_style(False)
        self.setText("📱 拖拽APK文件到此处安装\n\n支持 .apk 格式")
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if file_path.lower().endswith('.apk'):
                    self.fileDropped.emit(file_path)
                    event.acceptProposedAction()
                    return
        event.ignore()


class PythonHighlighter(QtGui.QSyntaxHighlighter):
    """Python 语法高亮器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighting_rules = []

        # 关键字
        keyword_format = QtGui.QTextCharFormat()
        keyword_format.setForeground(QtGui.QColor("#c678dd"))  # 紫色
        keyword_format.setFontWeight(QtGui.QFont.Bold)
        keywords = [
            "and", "as", "assert", "async", "await", "break", "class", "continue",
            "def", "del", "elif", "else", "except", "finally", "for", "from",
            "global", "if", "import", "in", "is", "lambda", "None", "nonlocal",
            "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
            "True", "False"
        ]
        for word in keywords:
            pattern = QtCore.QRegularExpression(rf"\b{word}\b")
            self._highlighting_rules.append((pattern, keyword_format))

        # 内置函数
        builtin_format = QtGui.QTextCharFormat()
        builtin_format.setForeground(QtGui.QColor("#61afef"))  # 蓝色
        builtins = [
            "abs", "all", "any", "bin", "bool", "bytes", "callable", "chr", "dict",
            "dir", "divmod", "enumerate", "eval", "exec", "filter", "float", "format",
            "getattr", "globals", "hasattr", "hash", "help", "hex", "id", "input",
            "int", "isinstance", "issubclass", "iter", "len", "list", "locals", "map",
            "max", "min", "next", "object", "oct", "open", "ord", "pow", "print",
            "range", "repr", "reversed", "round", "set", "setattr", "slice", "sorted",
            "str", "sum", "super", "tuple", "type", "vars", "zip"
        ]
        for word in builtins:
            pattern = QtCore.QRegularExpression(rf"\b{word}\b")
            self._highlighting_rules.append((pattern, builtin_format))

        # 字符串（单引号和双引号）
        string_format = QtGui.QTextCharFormat()
        string_format.setForeground(QtGui.QColor("#98c379"))  # 绿色
        self._highlighting_rules.append(
            (QtCore.QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), string_format)
        )
        self._highlighting_rules.append(
            (QtCore.QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), string_format)
        )

        # 数字
        number_format = QtGui.QTextCharFormat()
        number_format.setForeground(QtGui.QColor("#d19a66"))  # 橙色
        self._highlighting_rules.append(
            (QtCore.QRegularExpression(r"\b[0-9]+\.?[0-9]*\b"), number_format)
        )

        # 注释
        comment_format = QtGui.QTextCharFormat()
        comment_format.setForeground(QtGui.QColor("#5c6370"))  # 灰色
        comment_format.setFontItalic(True)
        self._highlighting_rules.append(
            (QtCore.QRegularExpression(r"#[^\n]*"), comment_format)
        )

        # 函数定义
        function_format = QtGui.QTextCharFormat()
        function_format.setForeground(QtGui.QColor("#e5c07b"))  # 黄色
        self._highlighting_rules.append(
            (QtCore.QRegularExpression(r"\bdef\s+(\w+)"), function_format)
        )

        # 类定义
        class_format = QtGui.QTextCharFormat()
        class_format.setForeground(QtGui.QColor("#e5c07b"))  # 黄色
        class_format.setFontWeight(QtGui.QFont.Bold)
        self._highlighting_rules.append(
            (QtCore.QRegularExpression(r"\bclass\s+(\w+)"), class_format)
        )

        # self 和 cls
        self_format = QtGui.QTextCharFormat()
        self_format.setForeground(QtGui.QColor("#e06c75"))  # 红色
        self_format.setFontItalic(True)
        self._highlighting_rules.append(
            (QtCore.QRegularExpression(r"\bself\b"), self_format)
        )
        self._highlighting_rules.append(
            (QtCore.QRegularExpression(r"\bcls\b"), self_format)
        )

        # 装饰器
        decorator_format = QtGui.QTextCharFormat()
        decorator_format.setForeground(QtGui.QColor("#c678dd"))  # 紫色
        self._highlighting_rules.append(
            (QtCore.QRegularExpression(r"@\w+"), decorator_format)
        )

        # 多行字符串格式（用于 highlightBlock 中）
        self._multiline_string_format = string_format
        self._triple_single = QtCore.QRegularExpression(r"'''")
        self._triple_double = QtCore.QRegularExpression(r'"""')

    def highlightBlock(self, text):
        # 应用单行规则
        for pattern, fmt in self._highlighting_rules:
            match_iter = pattern.globalMatch(text)
            while match_iter.hasNext():
                match = match_iter.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

        # 处理多行字符串（三引号）
        self._handle_multiline_strings(text, '"""', 1)
        self._handle_multiline_strings(text, "'''", 2)

    def _handle_multiline_strings(self, text, delimiter, state):
        """处理多行字符串高亮"""
        # 如果之前的状态不是当前类型的多行字符串，检查是否需要开始
        if self.previousBlockState() != state:
            start_index = text.find(delimiter)
            if start_index == -1:
                return  # 这行没有这种三引号
        else:
            start_index = 0  # 从上一行延续

        while start_index >= 0:
            # 查找结束三引号
            if self.previousBlockState() == state and start_index == 0:
                # 从行首开始查找结束
                end_index = text.find(delimiter, 0)
            else:
                # 查找匹配的结束三引号
                end_index = text.find(delimiter, start_index + len(delimiter))

            if end_index == -1:
                # 没找到结束，整行都是字符串
                self.setCurrentBlockState(state)
                length = len(text) - start_index
            else:
                # 找到结束
                length = end_index - start_index + len(delimiter)
                self.setCurrentBlockState(0)

            self.setFormat(start_index, length, self._multiline_string_format)

            # 继续查找下一个开始
            if end_index >= 0:
                start_index = text.find(delimiter, end_index + len(delimiter))
            else:
                break


class CodeEditorDialog(QtWidgets.QDialog):
    """带语法高亮的代码编辑器对话框"""

    def __init__(self, parent=None, title="代码编辑器", code="", readonly=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(700, 500)
        self.resize(800, 600)

        layout = QtWidgets.QVBoxLayout(self)

        # 代码编辑器
        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setStyleSheet("""
            QPlainTextEdit {
                font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                background-color: #282c34;
                color: #abb2bf;
                border: 1px solid #3e4451;
                border-radius: 4px;
                padding: 8px;
                line-height: 1.5;
            }
        """)
        self.editor.setPlainText(code)
        self.editor.setReadOnly(readonly)

        # 设置 Tab 宽度为 4 个空格
        font_metrics = QtGui.QFontMetrics(self.editor.font())
        self.editor.setTabStopDistance(4 * font_metrics.horizontalAdvance(' '))

        # 应用语法高亮
        self.highlighter = PythonHighlighter(self.editor.document())

        # 行号显示标签
        self.status_label = QtWidgets.QLabel()
        self.status_label.setStyleSheet("color: #71717a; font-size: 12px;")
        self._update_status()
        self.editor.textChanged.connect(self._update_status)
        self.editor.cursorPositionChanged.connect(self._update_cursor_position)

        layout.addWidget(self.editor)
        layout.addWidget(self.status_label)

        # 按钮
        button_layout = QtWidgets.QHBoxLayout()

        if not readonly:
            validate_btn = QtWidgets.QPushButton("验证语法")
            validate_btn.clicked.connect(self._validate_syntax)
            button_layout.addWidget(validate_btn)

        button_layout.addStretch()

        if readonly:
            close_btn = QtWidgets.QPushButton("关闭")
            close_btn.clicked.connect(self.reject)
            button_layout.addWidget(close_btn)
        else:
            cancel_btn = QtWidgets.QPushButton("取消")
            cancel_btn.clicked.connect(self.reject)
            save_btn = QtWidgets.QPushButton("保存")
            save_btn.clicked.connect(self.accept)
            save_btn.setDefault(True)
            button_layout.addWidget(cancel_btn)
            button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _update_status(self):
        text = self.editor.toPlainText()
        lines = text.count('\n') + 1
        chars = len(text)
        self.status_label.setText(f"行数: {lines}  |  字符数: {chars}")

    def _update_cursor_position(self):
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        text = self.editor.toPlainText()
        total_lines = text.count('\n') + 1
        chars = len(text)
        self.status_label.setText(f"行 {line}, 列 {col}  |  共 {total_lines} 行, {chars} 字符")

    def _validate_syntax(self):
        code = self.editor.toPlainText()
        try:
            compile(code, "<string>", "exec")
            QtWidgets.QMessageBox.information(self, "验证成功", "语法正确，没有发现错误。")
        except SyntaxError as e:
            QtWidgets.QMessageBox.warning(
                self, "语法错误",
                f"第 {e.lineno} 行存在语法错误:\n{e.msg}"
            )

    def get_code(self) -> str:
        return self.editor.toPlainText()
