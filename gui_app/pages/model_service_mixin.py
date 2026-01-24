# -*- coding: utf-8 -*-
"""模型服务页面 Mixin - 处理模型服务配置的所有功能"""

from PySide6 import QtCore, QtGui, QtWidgets

from gui_app.custom_widgets import NoWheelComboBox, NoWheelSpinBox, NoWheelDoubleSpinBox
from gui_app.model_services import ModelServiceConfig, ModelProtocol


class ModelServiceMixin:
    """模型服务页面的 Mixin 类，包含所有模型服务相关的方法"""

    def _build_model_service(self):
        page = QtWidgets.QWidget()
        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # Create scroll area for the entire content
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(scroll_content)
        layout.setContentsMargins(20, 12, 20, 20)
        layout.setSpacing(16)

        # Header
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        header = QtWidgets.QLabel("模型服务")
        header.setObjectName("title")

        subtitle = QtWidgets.QLabel("配置和管理多个AI模型服务，支持智谱BigModel、ModelScope等")
        subtitle.setObjectName("subtitle")

        header_layout.addWidget(header)
        header_layout.addWidget(subtitle)

        # Main content - 2 column layout
        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(16)

        # Left Panel - Services List
        left_card = QtWidgets.QFrame()
        left_card.setObjectName("card")
        left_card.setMinimumWidth(280)
        left_card.setMaximumWidth(350)
        left_layout = QtWidgets.QVBoxLayout(left_card)
        left_layout.setContentsMargins(16, 12, 16, 12)
        left_layout.setSpacing(10)

        list_header = QtWidgets.QLabel("服务列表")
        list_header.setObjectName("cardTitle")

        self.service_list = QtWidgets.QListWidget()
        self.service_list.setMinimumHeight(200)
        self.service_list.currentRowChanged.connect(self._on_service_selected)

        # Service list buttons
        list_btn_layout = QtWidgets.QHBoxLayout()
        list_btn_layout.setSpacing(6)

        self.add_service_btn = QtWidgets.QPushButton("添加")
        self.add_service_btn.setObjectName("secondary")
        self.add_service_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.add_service_btn.clicked.connect(self._add_new_service)

        self.delete_service_btn = QtWidgets.QPushButton("删除")
        self.delete_service_btn.setObjectName("danger")
        self.delete_service_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.delete_service_btn.clicked.connect(self._delete_current_service)

        self.activate_service_btn = QtWidgets.QPushButton("激活")
        self.activate_service_btn.setObjectName("success")
        self.activate_service_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.activate_service_btn.clicked.connect(self._activate_current_service)

        list_btn_layout.addWidget(self.add_service_btn)
        list_btn_layout.addWidget(self.delete_service_btn)
        list_btn_layout.addWidget(self.activate_service_btn)

        # Preset templates - 按协议分组
        preset_header = QtWidgets.QLabel("快速添加模板")
        preset_header.setStyleSheet("color: #71717a; font-size: 12px; margin-top: 10px;")

        self.preset_combo = NoWheelComboBox()
        self.preset_combo.addItem("选择预置模板...")
        # 按协议分组显示预设模板
        grouped_presets = self.model_services_manager.get_preset_templates_grouped()
        for category, presets in grouped_presets.items():
            # 添加分组标题（禁用项作为分隔符）
            separator_item = f"── {category} ──"
            self.preset_combo.addItem(separator_item, None)
            # 设置分组标题样式（禁用选择）
            idx = self.preset_combo.count() - 1
            self.preset_combo.model().item(idx).setEnabled(False)
            self.preset_combo.model().item(idx).setForeground(QtGui.QColor("#6366f1"))
            # 添加该分组下的预设
            for preset in presets:
                self.preset_combo.addItem(f"  {preset.name}", preset.id)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)

        left_layout.addWidget(list_header)
        left_layout.addWidget(self.service_list)
        left_layout.addLayout(list_btn_layout)
        left_layout.addWidget(preset_header)
        left_layout.addWidget(self.preset_combo)
        left_layout.addStretch()

        # Right Panel - Service Details
        right_card = QtWidgets.QFrame()
        right_card.setObjectName("card")
        right_layout = QtWidgets.QVBoxLayout(right_card)
        right_layout.setContentsMargins(16, 12, 16, 12)
        right_layout.setSpacing(12)

        detail_header = QtWidgets.QLabel("服务配置")
        detail_header.setObjectName("cardTitle")

        # Service status badge
        self.service_status_label = QtWidgets.QLabel("未选择服务")
        self.service_status_label.setStyleSheet(
            "font-size: 12px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
            "padding: 6px 12px; border-radius: 6px;"
        )

        # Form
        form = QtWidgets.QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)

        self.service_name_input = QtWidgets.QLineEdit()
        self.service_name_input.setPlaceholderText("服务显示名称")

        self.base_url_input = QtWidgets.QLineEdit()
        self.base_url_input.setPlaceholderText("http://localhost:8000/v1")
        self.base_url_input.textChanged.connect(self._on_base_url_changed)

        # 协议选择器
        self.protocol_combo = NoWheelComboBox()
        self.protocol_combo.addItem("OpenAI 协议", ModelProtocol.OPENAI.value)
        self.protocol_combo.addItem("Anthropic 协议", ModelProtocol.ANTHROPIC.value)
        self.protocol_combo.addItem("Gemini 协议", ModelProtocol.GEMINI.value)

        self.model_input = QtWidgets.QLineEdit()
        self.model_input.setPlaceholderText("autoglm-phone-9b")

        self.api_key_input = QtWidgets.QLineEdit()
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.api_key_input.setPlaceholderText("您的API密钥（可选）")

        self.service_desc_input = QtWidgets.QLineEdit()
        self.service_desc_input.setPlaceholderText("服务描述（可选）")

        # Advanced settings (collapsible idea - just show key ones)
        self.max_tokens_input = NoWheelSpinBox()
        self.max_tokens_input.setRange(100, 10000)
        self.max_tokens_input.setValue(3000)

        self.temperature_input = NoWheelDoubleSpinBox()
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setSingleStep(0.1)
        self.temperature_input.setValue(0.0)

        form.addRow("服务名称", self.service_name_input)
        form.addRow("服务地址", self.base_url_input)
        form.addRow("协议类型", self.protocol_combo)
        form.addRow("模型名称", self.model_input)
        form.addRow("API密钥", self.api_key_input)
        form.addRow("描述", self.service_desc_input)
        form.addRow("最大Token", self.max_tokens_input)
        form.addRow("Temperature", self.temperature_input)

        # Action Buttons
        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(10)

        self.save_service_btn = QtWidgets.QPushButton("保存配置")
        self.save_service_btn.setObjectName("success")
        self.save_service_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.save_service_btn.clicked.connect(self._save_current_service)

        self.test_service_btn = QtWidgets.QPushButton("测试连接")
        self.test_service_btn.setObjectName("secondary")
        self.test_service_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.test_service_btn.clicked.connect(self._test_current_service)

        actions.addWidget(self.save_service_btn)
        actions.addWidget(self.test_service_btn)
        actions.addStretch()

        right_layout.addWidget(detail_header)
        right_layout.addWidget(self.service_status_label)
        right_layout.addLayout(form)
        right_layout.addLayout(actions)
        right_layout.addStretch()

        content_layout.addWidget(left_card)
        content_layout.addWidget(right_card, 1)

        # Global Settings Card (max_steps and lang are global)
        global_card = QtWidgets.QFrame()
        global_card.setObjectName("card")
        global_layout = QtWidgets.QVBoxLayout(global_card)
        global_layout.setContentsMargins(16, 12, 16, 12)
        global_layout.setSpacing(10)

        global_header = QtWidgets.QLabel("全局设置")
        global_header.setObjectName("cardTitle")

        global_form = QtWidgets.QHBoxLayout()
        global_form.setSpacing(20)

        max_steps_label = QtWidgets.QLabel("最大步数:")
        self.max_steps_input = NoWheelSpinBox()
        self.max_steps_input.setRange(1, 500)
        self.max_steps_input.setValue(100)
        self.max_steps_input.setFixedWidth(100)

        lang_label = QtWidgets.QLabel("语言:")
        self.lang_combo = NoWheelComboBox()
        self.lang_combo.addItems(["cn", "en"])
        self.lang_combo.setFixedWidth(80)

        global_form.addWidget(max_steps_label)
        global_form.addWidget(self.max_steps_input)
        global_form.addSpacing(20)
        global_form.addWidget(lang_label)
        global_form.addWidget(self.lang_combo)
        global_form.addStretch()

        self.save_global_btn = QtWidgets.QPushButton("保存全局设置")
        self.save_global_btn.setObjectName("secondary")
        self.save_global_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.save_global_btn.clicked.connect(self._save_settings)

        global_layout.addWidget(global_header)
        global_layout.addLayout(global_form)
        global_layout.addWidget(self.save_global_btn, alignment=QtCore.Qt.AlignLeft)

        layout.addWidget(header_widget)
        layout.addLayout(content_layout, 1)
        layout.addWidget(global_card)

        # Initialize service list
        self._refresh_service_list()

        scroll_area.setWidget(scroll_content)
        page_layout.addWidget(scroll_area)

        return page

    def _refresh_service_list(self):
        """刷新服务列表"""
        self.service_list.clear()
        services = self.model_services_manager.get_all_services()
        for service in services:
            prefix = "✓ " if service.is_active else "  "
            item = QtWidgets.QListWidgetItem(f"{prefix}{service.name}")
            item.setData(QtCore.Qt.UserRole, service.id)
            if service.is_active:
                item.setForeground(QtGui.QColor("#10b981"))
            self.service_list.addItem(item)

        # Select the active service
        active = self.model_services_manager.get_active_service()
        if active:
            for i in range(self.service_list.count()):
                item = self.service_list.item(i)
                if item.data(QtCore.Qt.UserRole) == active.id:
                    self.service_list.setCurrentRow(i)
                    break

    def _on_service_selected(self, row):
        """服务选择变化时更新详情"""
        if row < 0:
            self._clear_service_form()
            return

        item = self.service_list.item(row)
        if not item:
            return

        service_id = item.data(QtCore.Qt.UserRole)
        service = self.model_services_manager.get_service_by_id(service_id)
        if service:
            self._load_service_to_form(service)

    def _load_service_to_form(self, service: ModelServiceConfig):
        """将服务配置加载到表单"""
        self.service_name_input.setText(service.name)
        self.base_url_input.setText(service.base_url)
        self.model_input.setText(service.model_name)
        self.api_key_input.setText(service.api_key)
        self.service_desc_input.setText(service.description)
        self.max_tokens_input.setValue(service.max_tokens)
        self.temperature_input.setValue(service.temperature)

        # 设置协议类型
        protocol = service.protocol or ModelProtocol.OPENAI.value
        for i in range(self.protocol_combo.count()):
            if self.protocol_combo.itemData(i) == protocol:
                self.protocol_combo.setCurrentIndex(i)
                break

        if service.is_active:
            self.service_status_label.setText("✓ 当前激活的服务")
            self.service_status_label.setStyleSheet(
                "font-size: 12px; color: #10b981; background: rgba(16, 185, 129, 0.15); "
                "padding: 6px 12px; border-radius: 6px;"
            )
        else:
            self.service_status_label.setText("未激活")
            self.service_status_label.setStyleSheet(
                "font-size: 12px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
                "padding: 6px 12px; border-radius: 6px;"
            )

    def _clear_service_form(self):
        """清空服务表单"""
        self.service_name_input.clear()
        self.base_url_input.clear()
        self.model_input.clear()
        self.api_key_input.clear()
        self.service_desc_input.clear()
        self.max_tokens_input.setValue(3000)
        self.temperature_input.setValue(0.0)
        self.protocol_combo.setCurrentIndex(0)  # 默认 OpenAI 协议
        self.service_status_label.setText("未选择服务")
        self.service_status_label.setStyleSheet(
            "font-size: 12px; color: #a1a1aa; background: rgba(39, 39, 42, 0.6); "
            "padding: 6px 12px; border-radius: 6px;"
        )

    def _get_current_service_id(self) -> str:
        """获取当前选中的服务ID"""
        current = self.service_list.currentItem()
        if current:
            return current.data(QtCore.Qt.UserRole)
        return ""

    def _save_current_service(self):
        """保存当前服务配置"""
        service_id = self._get_current_service_id()
        if not service_id:
            self._append_log("请先选择一个服务。\n")
            return

        service = self.model_services_manager.get_service_by_id(service_id)
        if not service:
            return

        # Update from form
        service.name = self.service_name_input.text().strip() or "未命名服务"
        service.base_url = self.base_url_input.text().strip()
        service.model_name = self.model_input.text().strip()
        service.api_key = self.api_key_input.text().strip()
        service.description = self.service_desc_input.text().strip()
        service.max_tokens = self.max_tokens_input.value()
        service.temperature = self.temperature_input.value()
        service.protocol = self.protocol_combo.currentData() or ModelProtocol.OPENAI.value

        self.model_services_manager.update_service(service)
        self._refresh_service_list()
        self._append_log(f"服务 [{service.name}] 配置已保存。\n")
        self._refresh_dashboard()

    def _test_current_service(self):
        """测试当前服务连接"""
        service_id = self._get_current_service_id()
        if not service_id:
            self._append_log("请先选择一个服务。\n")
            return

        # Create temp config from form
        temp_service = ModelServiceConfig(
            id="temp",
            name=self.service_name_input.text().strip(),
            base_url=self.base_url_input.text().strip(),
            api_key=self.api_key_input.text().strip(),
            model_name=self.model_input.text().strip(),
        )

        self.service_status_label.setText("测试中...")
        self.service_status_label.setStyleSheet(
            "font-size: 12px; color: #6366f1; background: rgba(99, 102, 241, 0.15); "
            "padding: 6px 12px; border-radius: 6px;"
        )
        QtWidgets.QApplication.processEvents()

        success, message = self.model_services_manager.test_service(temp_service)

        if success:
            self.service_status_label.setText(f"✓ {message}")
            self.service_status_label.setStyleSheet(
                "font-size: 12px; color: #10b981; background: rgba(16, 185, 129, 0.15); "
                "padding: 6px 12px; border-radius: 6px;"
            )
        else:
            self.service_status_label.setText(f"✗ {message}")
            self.service_status_label.setStyleSheet(
                "font-size: 12px; color: #ef4444; background: rgba(239, 68, 68, 0.15); "
                "padding: 6px 12px; border-radius: 6px;"
            )

        self._append_log(f"测试服务连接: {message}\n")

    def _add_new_service(self):
        """添加新服务"""
        new_service = ModelServiceConfig(
            name="新服务",
            base_url="http://localhost:8000/v1",
            model_name="autoglm-phone-9b",
            api_key="",
            description="",
        )
        self.model_services_manager.add_service(new_service)
        self._refresh_service_list()

        # Select the new service
        for i in range(self.service_list.count()):
            item = self.service_list.item(i)
            if item.data(QtCore.Qt.UserRole) == new_service.id:
                self.service_list.setCurrentRow(i)
                break

        self._append_log("已添加新服务，请配置详细信息。\n")

    def _delete_current_service(self):
        """删除当前服务"""
        service_id = self._get_current_service_id()
        if not service_id:
            return

        services = self.model_services_manager.get_all_services()
        if len(services) <= 1:
            self._append_log("至少需要保留一个服务。\n")
            return

        service = self.model_services_manager.get_service_by_id(service_id)
        if service:
            reply = QtWidgets.QMessageBox.question(
                self,
                "确认删除",
                f"确定要删除服务 [{service.name}] 吗？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.Yes:
                self.model_services_manager.delete_service(service_id)
                self._refresh_service_list()
                self._append_log(f"服务 [{service.name}] 已删除。\n")

    def _activate_current_service(self):
        """激活当前服务"""
        service_id = self._get_current_service_id()
        if not service_id:
            return

        self.model_services_manager.activate_service(service_id)
        self._refresh_service_list()

        service = self.model_services_manager.get_service_by_id(service_id)
        if service:
            self._append_log(f"服务 [{service.name}] 已激活。\n")
            self._load_service_to_form(service)
            self._refresh_dashboard()

    def _on_preset_selected(self, index):
        """从预置模板创建服务"""
        if index <= 0:
            return

        preset_id = self.preset_combo.itemData(index)
        if preset_id:
            new_service = self.model_services_manager.create_from_preset(preset_id)
            if new_service:
                self.model_services_manager.add_service(new_service)
                self._refresh_service_list()

                # Select the new service
                for i in range(self.service_list.count()):
                    item = self.service_list.item(i)
                    if item.data(QtCore.Qt.UserRole) == new_service.id:
                        self.service_list.setCurrentRow(i)
                        break

                self._append_log(f"已从模板创建服务 [{new_service.name}]。\n")

        # Reset combo
        self.preset_combo.setCurrentIndex(0)

    def _on_base_url_changed(self, url: str):
        """当服务地址改变时，自动检测并建议协议类型"""
        if not url.strip():
            return

        # 自动检测协议
        detected_protocol = self.model_services_manager.auto_detect_protocol(url)

        # 更新协议选择器
        for i in range(self.protocol_combo.count()):
            if self.protocol_combo.itemData(i) == detected_protocol:
                if self.protocol_combo.currentIndex() != i:
                    self.protocol_combo.setCurrentIndex(i)
                break
