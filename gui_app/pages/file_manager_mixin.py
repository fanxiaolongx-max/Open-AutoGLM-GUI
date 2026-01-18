# -*- coding: utf-8 -*-
"""文件管理页面 Mixin - 处理设备文件管理的所有功能"""

import subprocess

from PySide6 import QtCore, QtWidgets


class FileManagerMixin:
    """文件管理页面的 Mixin 类，包含所有文件管理相关的方法"""

    def _build_file_manager(self):
        """构建文件管理页面"""
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(16)

        # Header
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 8)
        header_layout.setSpacing(4)

        header = QtWidgets.QLabel("📁 文件管理")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("通过 ADB 管理设备文件系统")
        subtitle.setObjectName("subtitle")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Toolbar - 设备选择
        device_toolbar = QtWidgets.QHBoxLayout()
        device_toolbar.setSpacing(8)

        device_label = QtWidgets.QLabel("设备:")
        device_label.setStyleSheet("font-size: 13px; color: #a1a1aa;")

        self.file_device_combo = QtWidgets.QComboBox()
        self.file_device_combo.setMinimumWidth(200)
        self.file_device_combo.setPlaceholderText("选择设备...")
        self.file_device_combo.currentIndexChanged.connect(self._file_manager_device_changed)

        refresh_device_btn = QtWidgets.QPushButton("刷新设备")
        refresh_device_btn.setObjectName("secondary")
        refresh_device_btn.setCursor(QtCore.Qt.PointingHandCursor)
        refresh_device_btn.clicked.connect(self._file_manager_refresh_devices)

        device_toolbar.addWidget(device_label)
        device_toolbar.addWidget(self.file_device_combo)
        device_toolbar.addWidget(refresh_device_btn)
        device_toolbar.addStretch()

        # Toolbar - 路径导航
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(8)

        self.file_path_input = QtWidgets.QLineEdit()
        self.file_path_input.setPlaceholderText("输入路径，如 /sdcard/")
        self.file_path_input.setText("/sdcard/")
        self.file_path_input.returnPressed.connect(self._file_manager_navigate)

        go_btn = QtWidgets.QPushButton("前往")
        go_btn.setObjectName("primary")
        go_btn.setCursor(QtCore.Qt.PointingHandCursor)
        go_btn.clicked.connect(self._file_manager_navigate)

        refresh_btn = QtWidgets.QPushButton("🔄 刷新")
        refresh_btn.setObjectName("secondary")
        refresh_btn.setCursor(QtCore.Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._file_manager_refresh)

        parent_btn = QtWidgets.QPushButton("⬆️ 上级目录")
        parent_btn.setObjectName("secondary")
        parent_btn.setCursor(QtCore.Qt.PointingHandCursor)
        parent_btn.clicked.connect(self._file_manager_go_up)

        toolbar.addWidget(self.file_path_input, 1)
        toolbar.addWidget(go_btn)
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(parent_btn)

        # Content area
        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(12)

        # Quick access panel
        quick_card = QtWidgets.QFrame()
        quick_card.setObjectName("card")
        quick_card.setFixedWidth(180)
        quick_layout = QtWidgets.QVBoxLayout(quick_card)
        quick_layout.setContentsMargins(12, 12, 12, 12)
        quick_layout.setSpacing(4)

        quick_title = QtWidgets.QLabel("快速访问")
        quick_title.setObjectName("cardTitle")
        quick_layout.addWidget(quick_title)

        quick_paths = [
            ("📱 内部存储", "/sdcard/"),
            ("📸 相册", "/sdcard/DCIM/"),
            ("📥 下载", "/sdcard/Download/"),
            ("🎵 音乐", "/sdcard/Music/"),
            ("🎬 视频", "/sdcard/Movies/"),
            ("📄 文档", "/sdcard/Documents/"),
            ("📦 应用数据", "/data/data/"),
            ("⚙️ 系统", "/system/"),
        ]

        for label, path in quick_paths:
            btn = QtWidgets.QPushButton(label)
            btn.setObjectName("secondary")
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setToolTip(path)
            btn.clicked.connect(lambda checked, p=path: self._file_manager_go_to(p))
            quick_layout.addWidget(btn)

        quick_layout.addStretch()

        # File list panel
        file_card = QtWidgets.QFrame()
        file_card.setObjectName("card")
        file_layout = QtWidgets.QVBoxLayout(file_card)
        file_layout.setContentsMargins(12, 12, 12, 12)
        file_layout.setSpacing(8)

        file_title = QtWidgets.QLabel("文件列表")
        file_title.setObjectName("cardTitle")

        self.file_list = QtWidgets.QTreeWidget()
        self.file_list.setHeaderLabels(["名称", "大小", "权限", "修改时间"])
        self.file_list.setColumnWidth(0, 300)
        self.file_list.setColumnWidth(1, 100)
        self.file_list.setColumnWidth(2, 100)
        self.file_list.setColumnWidth(3, 150)
        self.file_list.setRootIsDecorated(False)
        self.file_list.setAlternatingRowColors(True)
        self.file_list.itemDoubleClicked.connect(self._file_manager_item_double_clicked)
        self.file_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._file_manager_context_menu)

        file_layout.addWidget(file_title)
        file_layout.addWidget(self.file_list, 1)

        # Action buttons
        action_layout = QtWidgets.QHBoxLayout()
        action_layout.setSpacing(8)

        upload_btn = QtWidgets.QPushButton("📤 上传文件")
        upload_btn.setObjectName("primary")
        upload_btn.setCursor(QtCore.Qt.PointingHandCursor)
        upload_btn.clicked.connect(self._file_manager_upload)

        download_btn = QtWidgets.QPushButton("📥 下载")
        download_btn.setObjectName("secondary")
        download_btn.setCursor(QtCore.Qt.PointingHandCursor)
        download_btn.clicked.connect(self._file_manager_download)

        new_folder_btn = QtWidgets.QPushButton("📁 新建文件夹")
        new_folder_btn.setObjectName("secondary")
        new_folder_btn.setCursor(QtCore.Qt.PointingHandCursor)
        new_folder_btn.clicked.connect(self._file_manager_new_folder)

        delete_btn = QtWidgets.QPushButton("🗑️ 删除")
        delete_btn.setObjectName("danger")
        delete_btn.setCursor(QtCore.Qt.PointingHandCursor)
        delete_btn.clicked.connect(self._file_manager_delete)

        action_layout.addWidget(upload_btn)
        action_layout.addWidget(download_btn)
        action_layout.addWidget(new_folder_btn)
        action_layout.addWidget(delete_btn)
        action_layout.addStretch()

        file_layout.addLayout(action_layout)

        # Status bar
        self.file_status = QtWidgets.QLabel("就绪")
        self.file_status.setStyleSheet(
            "font-size: 11px; color: #71717a; padding: 4px 8px;"
        )

        file_layout.addWidget(self.file_status)

        content_layout.addWidget(quick_card)
        content_layout.addWidget(file_card, 1)

        layout.addWidget(header_widget)
        layout.addLayout(device_toolbar)
        layout.addLayout(toolbar)
        layout.addLayout(content_layout, 1)

        # 初始化时刷新设备列表
        QtCore.QTimer.singleShot(500, self._file_manager_refresh_devices)

        return page

    def _file_manager_refresh_devices(self):
        """刷新文件管理器的设备列表"""
        self.file_device_combo.clear()

        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            lines = result.stdout.strip().split("\n")[1:]  # 跳过第一行 "List of devices attached"
            for line in lines:
                if "\tdevice" in line:
                    device_id = line.split("\t")[0]
                    self.file_device_combo.addItem(device_id, device_id)

            if self.file_device_combo.count() == 0:
                self.file_status.setText("未检测到设备，请连接设备后点击刷新")
            else:
                self.file_status.setText(f"检测到 {self.file_device_combo.count()} 个设备")

        except FileNotFoundError:
            self.file_status.setText("ADB 未安装，请先安装 Android SDK Platform Tools")
        except Exception as e:
            self.file_status.setText(f"获取设备列表失败: {str(e)}")

    def _file_manager_device_changed(self, index):
        """设备选择变化时刷新文件列表"""
        if index >= 0:
            self._file_manager_list_dir(self.file_path_input.text().strip())

    def _get_file_manager_device_id(self):
        """获取当前选择的设备ID"""
        if self.file_device_combo.count() > 0:
            return self.file_device_combo.currentData()
        return None

    def _file_manager_navigate(self):
        """导航到指定路径"""
        path = self.file_path_input.text().strip()
        if path:
            self._file_manager_list_dir(path)

    def _file_manager_refresh(self):
        """刷新当前目录"""
        path = self.file_path_input.text().strip()
        if path:
            self._file_manager_list_dir(path)

    def _file_manager_go_up(self):
        """返回上级目录"""
        path = self.file_path_input.text().strip()
        if path and path != "/":
            parent = "/".join(path.rstrip("/").split("/")[:-1])
            if not parent:
                parent = "/"
            self._file_manager_go_to(parent)

    def _file_manager_go_to(self, path):
        """跳转到指定路径"""
        self.file_path_input.setText(path)
        self._file_manager_list_dir(path)

    def _file_manager_list_dir(self, path):
        """列出目录内容"""
        self.file_list.clear()

        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return

        self.file_status.setText(f"正在加载: {path}")
        QtWidgets.QApplication.processEvents()

        adb_prefix = ["adb", "-s", device_id]

        try:
            # 使用 ls -la 获取详细信息
            result = subprocess.run(
                adb_prefix + ["shell", f"ls -la '{path}'"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                self.file_status.setText(f"错误: {result.stderr.strip()}")
                return

            lines = result.stdout.strip().split("\n")
            file_count = 0
            dir_count = 0

            for line in lines:
                if not line.strip() or line.startswith("total"):
                    continue

                parts = line.split()
                if len(parts) < 8:
                    continue

                perms = parts[0]
                size = parts[4] if len(parts) > 4 else "-"
                date = f"{parts[5]} {parts[6]}" if len(parts) > 6 else "-"
                name = " ".join(parts[7:]) if len(parts) > 7 else parts[-1]

                # 跳过 . 和 ..
                if name in [".", ".."]:
                    continue

                item = QtWidgets.QTreeWidgetItem()

                # 根据类型添加图标
                if perms.startswith("d"):
                    item.setText(0, f"📁 {name}")
                    item.setData(0, QtCore.Qt.UserRole, ("dir", name))
                    dir_count += 1
                elif perms.startswith("l"):
                    item.setText(0, f"🔗 {name}")
                    item.setData(0, QtCore.Qt.UserRole, ("link", name))
                else:
                    # 根据扩展名显示不同图标
                    ext = name.split(".")[-1].lower() if "." in name else ""
                    icon = self._get_file_icon(ext)
                    item.setText(0, f"{icon} {name}")
                    item.setData(0, QtCore.Qt.UserRole, ("file", name))
                    file_count += 1

                item.setText(1, self._format_size(size))
                item.setText(2, perms)
                item.setText(3, date)

                self.file_list.addTopLevelItem(item)

            self.file_status.setText(f"共 {dir_count} 个文件夹, {file_count} 个文件")

        except subprocess.TimeoutExpired:
            self.file_status.setText("操作超时")
        except Exception as e:
            self.file_status.setText(f"错误: {str(e)}")

    def _get_file_icon(self, ext):
        """根据扩展名返回文件图标"""
        icons = {
            "jpg": "🖼️", "jpeg": "🖼️", "png": "🖼️", "gif": "🖼️", "bmp": "🖼️", "webp": "🖼️",
            "mp4": "🎬", "mkv": "🎬", "avi": "🎬", "mov": "🎬", "wmv": "🎬",
            "mp3": "🎵", "wav": "🎵", "flac": "🎵", "aac": "🎵", "ogg": "🎵",
            "apk": "📦", "zip": "📦", "rar": "📦", "7z": "📦", "tar": "📦", "gz": "📦",
            "txt": "📄", "log": "📄", "md": "📄", "json": "📄", "xml": "📄",
            "pdf": "📕", "doc": "📘", "docx": "📘", "xls": "📗", "xlsx": "📗",
            "py": "🐍", "js": "📜", "html": "🌐", "css": "🎨",
        }
        return icons.get(ext, "📄")

    def _format_size(self, size_str):
        """格式化文件大小"""
        try:
            size = int(size_str)
            if size < 1024:
                return f"{size} B"
            elif size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            elif size < 1024 * 1024 * 1024:
                return f"{size / (1024 * 1024):.1f} MB"
            else:
                return f"{size / (1024 * 1024 * 1024):.2f} GB"
        except:
            return size_str

    def _file_manager_item_double_clicked(self, item, column):
        """双击项目"""
        data = item.data(0, QtCore.Qt.UserRole)
        if data:
            item_type, name = data
            if item_type == "dir":
                current_path = self.file_path_input.text().strip().rstrip("/")
                new_path = f"{current_path}/{name}"
                self._file_manager_go_to(new_path)

    def _file_manager_context_menu(self, position):
        """右键菜单"""
        item = self.file_list.itemAt(position)
        if not item:
            return

        menu = QtWidgets.QMenu()

        download_action = menu.addAction("📥 下载")
        rename_action = menu.addAction("✏️ 重命名")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ 删除")

        action = menu.exec_(self.file_list.mapToGlobal(position))

        if action == download_action:
            self._file_manager_download()
        elif action == rename_action:
            self._file_manager_rename()
        elif action == delete_action:
            self._file_manager_delete()

    def _file_manager_upload(self):
        """上传文件到设备"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择要上传的文件"
        )
        if not file_path:
            return

        device_path = self.file_path_input.text().strip()
        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return
        adb_prefix = ["adb", "-s", device_id]

        self.file_status.setText(f"正在上传: {file_path}")
        QtWidgets.QApplication.processEvents()

        try:
            result = subprocess.run(
                adb_prefix + ["push", file_path, device_path],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                self.file_status.setText("上传成功")
                self._file_manager_refresh()
            else:
                self.file_status.setText(f"上传失败: {result.stderr.strip()}")

        except Exception as e:
            self.file_status.setText(f"上传错误: {str(e)}")

    def _file_manager_download(self):
        """从设备下载文件"""
        item = self.file_list.currentItem()
        if not item:
            self.file_status.setText("请先选择要下载的文件")
            return

        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return

        item_type, name = data
        if item_type == "dir":
            self.file_status.setText("暂不支持下载文件夹")
            return

        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "保存文件", name
        )
        if not save_path:
            return

        device_path = self.file_path_input.text().strip().rstrip("/") + "/" + name
        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return
        adb_prefix = ["adb", "-s", device_id]

        self.file_status.setText(f"正在下载: {name}")
        QtWidgets.QApplication.processEvents()

        try:
            result = subprocess.run(
                adb_prefix + ["pull", device_path, save_path],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                self.file_status.setText(f"下载成功: {save_path}")
            else:
                self.file_status.setText(f"下载失败: {result.stderr.strip()}")

        except Exception as e:
            self.file_status.setText(f"下载错误: {str(e)}")

    def _file_manager_new_folder(self):
        """新建文件夹"""
        name, ok = QtWidgets.QInputDialog.getText(
            self, "新建文件夹", "请输入文件夹名称:"
        )
        if not ok or not name:
            return

        device_path = self.file_path_input.text().strip().rstrip("/") + "/" + name
        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return
        adb_prefix = ["adb", "-s", device_id]

        try:
            result = subprocess.run(
                adb_prefix + ["shell", f"mkdir -p '{device_path}'"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                self.file_status.setText(f"文件夹创建成功: {name}")
                self._file_manager_refresh()
            else:
                self.file_status.setText(f"创建失败: {result.stderr.strip()}")

        except Exception as e:
            self.file_status.setText(f"创建错误: {str(e)}")

    def _file_manager_delete(self):
        """删除文件或文件夹"""
        item = self.file_list.currentItem()
        if not item:
            self.file_status.setText("请先选择要删除的项目")
            return

        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return

        item_type, name = data

        reply = QtWidgets.QMessageBox.question(
            self, "确认删除",
            f"确定要删除 '{name}' 吗？\n此操作不可恢复！",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        device_path = self.file_path_input.text().strip().rstrip("/") + "/" + name
        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return
        adb_prefix = ["adb", "-s", device_id]

        # 使用 -rf 删除文件夹
        rm_cmd = "rm -rf" if item_type == "dir" else "rm"

        try:
            result = subprocess.run(
                adb_prefix + ["shell", f"{rm_cmd} '{device_path}'"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                self.file_status.setText(f"删除成功: {name}")
                self._file_manager_refresh()
            else:
                self.file_status.setText(f"删除失败: {result.stderr.strip()}")

        except Exception as e:
            self.file_status.setText(f"删除错误: {str(e)}")

    def _file_manager_rename(self):
        """重命名文件或文件夹"""
        item = self.file_list.currentItem()
        if not item:
            return

        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return

        item_type, old_name = data

        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "重命名", "请输入新名称:", text=old_name
        )
        if not ok or not new_name or new_name == old_name:
            return

        base_path = self.file_path_input.text().strip().rstrip("/")
        old_path = f"{base_path}/{old_name}"
        new_path = f"{base_path}/{new_name}"
        device_id = self._get_file_manager_device_id()
        if not device_id:
            self.file_status.setText("请先选择设备")
            return
        adb_prefix = ["adb", "-s", device_id]

        try:
            result = subprocess.run(
                adb_prefix + ["shell", f"mv '{old_path}' '{new_path}'"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                self.file_status.setText(f"重命名成功: {old_name} → {new_name}")
                self._file_manager_refresh()
            else:
                self.file_status.setText(f"重命名失败: {result.stderr.strip()}")

        except Exception as e:
            self.file_status.setText(f"重命名错误: {str(e)}")
