    # ============ MENU SYSTEM ============
    
    def _add_back_button(self, keyboard: list, back_to: str = "main_menu") -> None:
        """Add back and home buttons to keyboard."""
        keyboard.append([
            InlineKeyboardButton("◀️ 返回", callback_data=back_to),
            InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")
        ])
    
    async def _show_main_menu(self, query_or_update, is_query: bool = True):
        """Show the main menu with all categories."""
        text = """
🏠 **AutoGLM 主菜单**

请选择功能分类：
"""
        
        keyboard = [
            [
                InlineKeyboardButton("📋 任务管理", callback_data="menu_tasks"),
                InlineKeyboardButton("📱 设备管理", callback_data="menu_devices"),
            ],
            [
                InlineKeyboardButton("⚙️ 系统设置", callback_data="menu_settings"),
                InlineKeyboardButton("🤖 模型配置", callback_data="menu_models"),
            ],
            [
                InlineKeyboardButton("📊 高级功能", callback_data="menu_advanced"),
                InlineKeyboardButton("ℹ️ 帮助支持", callback_data="menu_help"),
            ],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if is_query:
            await query_or_update.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query_or_update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_tasks_menu(self, query):
        """Show tasks management menu."""
        text = """
📋 **任务管理**

管理和执行自动化任务：
"""
        
        keyboard = [
            [InlineKeyboardButton("▶️ 执行任务", callback_data="get_task")],
            [InlineKeyboardButton("📸 获取截图", callback_data="get_screenshot")],
            [InlineKeyboardButton("📅 定时任务", callback_data="tasks_scheduled")],
            [InlineKeyboardButton("📜 任务历史", callback_data="tasks_history")],
            [InlineKeyboardButton("💬 Chat 对话", callback_data="tasks_chat")],
        ]
        
        self._add_back_button(keyboard)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_devices_menu(self, query):
        """Show device management menu."""
        text = """
📱 **设备管理**

管理连接的设备和应用：
"""
        
        keyboard = [
            [InlineKeyboardButton("📱 设备列表", callback_data="show_devices")],
            [InlineKeyboardButton("➕ 添加设备", callback_data="devices_add")],
            [InlineKeyboardButton("🔓 设备解锁", callback_data="devices_unlock")],
            [InlineKeyboardButton("📦 应用管理", callback_data="devices_apps")],
            [InlineKeyboardButton("📁 文件管理", callback_data="devices_files")],
        ]
        
        self._add_back_button(keyboard)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_settings_menu(self, query):
        """Show system settings menu."""
        text = """
⚙️ **系统设置**

配置系统参数和通知：
"""
        
        keyboard = [
            [InlineKeyboardButton("📧 邮件通知", callback_data="settings_email")],
            [InlineKeyboardButton("🔐 Telegram 权限", callback_data="settings_telegram")],
            [InlineKeyboardButton("📊 日志设置", callback_data="settings_logs")],
            [InlineKeyboardButton("🎨 UI 设置", callback_data="settings_ui")],
        ]
        
        self._add_back_button(keyboard)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_models_menu(self, query):
        """Show model configuration menu."""
        text = """
🤖 **模型配置**

管理 AI 模型和参数：
"""
        
        keyboard = [
            [InlineKeyboardButton("🎯 选择模型", callback_data="models_select")],
            [InlineKeyboardButton("⚡ 模型参数", callback_data="models_params")],
            [InlineKeyboardButton("🔑 API 密钥", callback_data="models_api")],
        ]
        
        self._add_back_button(keyboard)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_advanced_menu(self, query):
        """Show advanced features menu."""
        text = """
📊 **高级功能**

规则、诊断和统计：
"""
        
        keyboard = [
            [InlineKeyboardButton("📏 规则配置", callback_data="advanced_rules")],
            [InlineKeyboardButton("🔍 系统诊断", callback_data="advanced_diagnostic")],
            [InlineKeyboardButton("📈 统计信息", callback_data="advanced_stats")],
        ]
        
        self._add_back_button(keyboard)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_help_menu(self, query):
        """Show help and support menu."""
        text = """
ℹ️ **帮助支持**

获取帮助和了解更新：
"""
        
        keyboard = [
            [InlineKeyboardButton("📖 使用指南", callback_data="help_guide")],
            [InlineKeyboardButton("💡 快速开始", callback_data="help_quickstart")],
            [InlineKeyboardButton("🐛 问题反馈", callback_data="help_feedback")],
            [InlineKeyboardButton("📝 更新日志", callback_data="help_changelog")],
        ]
        
        self._add_back_button(keyboard)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_feature_stub(self, query, feature_name: str):
        """Handle placeholder for unimplemented features."""
        await query.answer(
            f"🚧 {feature_name} 功能开发中，敬请期待！",
            show_alert=True
        )
        # Don't change the current menu
