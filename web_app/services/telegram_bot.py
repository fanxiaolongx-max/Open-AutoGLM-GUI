# -*- coding: utf-8 -*-
"""
Telegram Bot service for remote task execution and monitoring.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

logger = logging.getLogger(__name__)


class TelegramBotService:
    """Telegram Bot service for remote control."""

    def __init__(self):
        self._application: Optional[Application] = None
        self._bot_token: Optional[str] = None
        self._enabled: bool = False
        self._allowed_users: list[int] = []
        self._running: bool = False
        self._config: Dict[str, Any] = {}  # Store config for use in commands
        # Store pending tasks and device selections
        self._pending_tasks: Dict[str, str] = {}  # user_id -> task_content
        self._selected_devices: Dict[str, set] = {}  # user_id -> set of device_ids
        self._pending_action: Dict[str, str] = {}  # user_id -> action (task/screenshot)
        self._task_options: Dict[str, Dict[str, bool]] = {}  # chat_id -> {complex_task: bool, send_email: bool}
        self._menu_stack: Dict[str, list] = {}  # chat_id -> menu history for breadcrumb

    async def start(self, config: Dict[str, Any]):
        """Start the Telegram bot."""
        self._bot_token = config.get("bot_token")
        self._enabled = config.get("enabled", False)
        self._allowed_users = config.get("allowed_users", [])
        self._config = config  # Store config

        if not self._enabled or not self._bot_token:
            logger.info("Telegram bot is disabled or not configured")
            return

        try:
            # Create application
            self._application = Application.builder().token(self._bot_token).build()

            # Register command handlers
            self._application.add_handler(CommandHandler("start", self._cmd_start))
            self._application.add_handler(CommandHandler("help", self._cmd_help))
            self._application.add_handler(CommandHandler("task", self._cmd_task))
            self._application.add_handler(CommandHandler("status", self._cmd_status))
            self._application.add_handler(CommandHandler("devices", self._cmd_devices))
            self._application.add_handler(CommandHandler("screenshot", self._cmd_screenshot))
            self._application.add_handler(CommandHandler("config", self._cmd_config))
            self._application.add_handler(CallbackQueryHandler(self._button_callback))
            
            # Handle all non-command text messages
            self._application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

            # Start polling
            await self._application.initialize()
            await self._application.start()
            await self._application.updater.start_polling()
            self._running = True
            logger.info("✅ Telegram bot started successfully")

        except Exception as e:
            logger.error(f"❌ Failed to start Telegram bot: {e}")
            raise

    async def stop(self):
        """Stop the Telegram bot."""
        if self._application and self._running:
            try:
                await self._application.updater.stop()
                await self._application.stop()
                await self._application.shutdown()
                self._running = False
                logger.info("Telegram bot stopped")
            except Exception as e:
                logger.error(f"Error stopping Telegram bot: {e}")

    def _check_authorization(self, user_id: int) -> bool:
        """Check if user is authorized."""
        return not self._allowed_users or user_id in self._allowed_users

    def _escape_markdown(self, text: str) -> str:
        """Escape markdown special characters."""
        if not text:
            return ""
        return text.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user_id = update.effective_user.id
        
        if not self._check_authorization(user_id):
            await update.message.reply_text("❌ 未授权的用户")
            return

        # Show new main menu
        await self._show_main_menu(update, is_query=False)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not self._check_authorization(update.effective_user.id):
            await update.message.reply_text("❌ 未授权的用户")
            return

        help_text = """
📚 **命令帮助**

**任务控制：**
`/task <指令>` - 执行手机自动化任务
   示例：/task 打开微信

**状态查询：**
`/status` - 查看当前任务状态
`/devices` - 列出所有连接的设备
`/screenshot` - 获取当前设备截图

**配置选项：**
`/config complex on` - 开启复杂任务模式
`/config complex off` - 关闭复杂任务模式
`/config email on` - 开启邮件通知
`/config email off` - 关闭邮件通知
`/config debug on` - 开启调试模式
`/config debug off` - 关闭调试模式

**其他：**
`/help` - 显示此帮助信息
"""
        # Add main menu button
        keyboard = [[InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle non-command text messages - check for task input or show welcome menu."""
        user_id = update.effective_user.id
        chat_id = str(update.message.chat_id)
        
        if not self._check_authorization(user_id):
            await update.message.reply_text("❌ 未授权的用户")
            return

        # Check if user is in task input mode
        if chat_id in self._pending_action and self._pending_action[chat_id] == "task":
            # User is inputting a task, handle it like /task command
            task_content = update.message.text.strip()
            
            from web_app.services.device_service import device_service
            
            # Get available devices
            devices = device_service.get_all_devices()
            if not devices:
                await update.message.reply_text("❌ 没有可用的设备")
                return
            
            # Store task for this chat
            self._pending_tasks[chat_id] = task_content
            self._selected_devices[chat_id] = set()  # Reset selection
            # Keep pending_action as "task"
            
            # Create device selection buttons
            keyboard = []
            for device in devices:
                status_emoji = "🟢" if device.status == "online" else "🔴"
                device_label = f"{status_emoji} {device.id[:12]}..."
                if device.name:
                    device_label = f"{status_emoji} {device.name[:15]}"
                
                keyboard.append([InlineKeyboardButton(
                    device_label,
                    callback_data=f"select_device_{device.id}"
                )])
            
            keyboard.append([
                InlineKeyboardButton("✅ 全选", callback_data="select_all_devices"),
                InlineKeyboardButton("🔄 清除", callback_data="clear_devices"),
            ])
            keyboard.append([InlineKeyboardButton("▶️ 执行任务", callback_data="execute_task")])
            keyboard.append([InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Escape markdown special characters
            task_content_safe = task_content.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
            
            await update.message.reply_text(
                f"📝 **任务:** {task_content_safe}\n\n"
                f"📱 请选择要执行任务的设备\n"
                f"💡 点击设备进行选择",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        # Show new main menu
        await self._show_main_menu(update, is_query=False)

    async def _cmd_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /task command - show device selection."""
        if not self._check_authorization(update.effective_user.id):
            await update.message.reply_text("❌ 未授权的用户")
            return

        if not context.args:
            await update.message.reply_text("❌ 请提供任务指令\n示例: /task 打开微信")
            return

        task_content = " ".join(context.args)
        # Use chat_id to support both private and group chats
        chat_id = str(update.effective_chat.id)
        
        try:
            # Import services
            from web_app.services.device_service import device_service
            
            # Get available devices
            devices = device_service.get_all_devices()
            if not devices:
                await update.message.reply_text("❌ 没有可用的设备")
                return
            
            # Store task for this chat
            self._pending_tasks[chat_id] = task_content
            self._selected_devices[chat_id] = set()  # Reset selection
            self._pending_action[chat_id] = "task"  # Mark as task action
            
            # Create device selection buttons (max 8 per row for better UX)
            keyboard = []
            for device in devices:
                status_emoji = "🟢" if device.status == "online" else "🔴"
                device_label = f"{status_emoji} {device.id[:12]}..."
                if device.name:
                    device_label = f"{status_emoji} {device.name[:15]}"
                
                keyboard.append([InlineKeyboardButton(
                    device_label,
                    callback_data=f"select_device_{device.id}"
                )])
            
            # Add control buttons
            keyboard.append([
                InlineKeyboardButton("✅ 全选", callback_data="select_all_devices"),
                InlineKeyboardButton("🔄 清除", callback_data="clear_devices"),
            ])
            keyboard.append([
                InlineKeyboardButton("▶️ 执行任务", callback_data="execute_task"),
            ])
            keyboard.append([InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"📝 **任务:** {task_content}\n\n"
                f"📱 请选择要使用的设备 (点击可多选):\n"
                f"💡 选择后点击 '▶️ 执行任务'",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
                
        except Exception as e:
            logger.error(f"Task command failed: {e}")
            await update.message.reply_text(f"❌ 失败: {str(e)}")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self._check_authorization(update.effective_user.id):
            await update.message.reply_text("❌ 未授权的用户")
            return

        try:
            from web_app.services.task_service import task_service
            
            # Get current task
            current_task = task_service.get_current_task()
            
            if current_task and current_task.status == "running":
                response = "🔄 **任务运行中**\n\n"
                response += f"📝 任务: {current_task.task_content}\n"
                response += f"⏱️ 进度: {current_task.progress}%\n"
                response += f"📱 设备数: {len(current_task.device_ids)}\n"
                response += f"🕐 开始时间: {current_task.start_time}"
            else:
                response = "✅ 当前没有运行中的任务"
            
            # Add main menu button
            keyboard = [[InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Status query failed: {e}")
            await update.message.reply_text(f"❌ 查询失败: {str(e)}")

    async def _cmd_devices(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /devices command."""
        if not self._check_authorization(update.effective_user.id):
            await update.message.reply_text("❌ 未授权的用户")
            return

        try:
            from web_app.services.device_service import device_service
            
            devices = device_service.get_all_devices()
            
            if not devices:
                await update.message.reply_text("📱 没有连接的设备")
                return
            
            response = f"📱 **连接的设备** ({len(devices)})\n\n"
            for i, device in enumerate(devices, 1):
                # device.status is like "online" or "offline"
                status_emoji = "🟢" if device.status == "online" else "🔴"
                # Escape device ID for markdown
                device_id_safe = device.id.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
                response += f"{i}. {status_emoji} `{device_id_safe}`\n"
                if device.name:
                    device_name_safe = device.name.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
                    response += f"   📱 {device_name_safe}\n"
                if device.model:
                    device_model_safe = device.model.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
                    response += f"   📋 {device_model_safe}\n"
            
            await update.message.reply_text(response, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Device query failed: {e}")
            await update.message.reply_text(f"❌ 查询失败: {str(e)}")

    async def _cmd_screenshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /screenshot command - show device selection."""
        if not self._check_authorization(update.effective_user.id):
            await update.message.reply_text("❌ 未授权的用户")
            return

        # Use chat_id to support both private and group chats
        chat_id = str(update.effective_chat.id)
        
        try:
            from web_app.services.device_service import device_service
            
            devices = device_service.get_all_devices()
            if not devices:
                await update.message.reply_text("❌ 没有可用的设备")
                return
            
            # Store action for this chat
            self._pending_action[chat_id] = "screenshot"
            self._selected_devices[chat_id] = set()  # Reset selection
            
            # Create device selection buttons
            keyboard = []
            for device in devices:
                status_emoji = "🟢" if device.status == "online" else "🔴"
                device_label = f"{status_emoji} {device.id[:12]}..."
                if device.name:
                    device_label = f"{status_emoji} {device.name[:15]}"
                
                keyboard.append([InlineKeyboardButton(
                    device_label,
                    callback_data=f"select_device_{device.id}"
                )])
            
            # Add control buttons
            keyboard.append([
                InlineKeyboardButton("✅ 全选", callback_data="select_all_devices"),
                InlineKeyboardButton("🔄 清除", callback_data="clear_devices"),
            ])
            keyboard.append([
                InlineKeyboardButton("📸 获取截图", callback_data="execute_screenshot"),
            ])
            keyboard.append([InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"📸 **获取截图**\n\n"
                f"📱 请选择设备 (可多选):\n"
                f"💡 选择后点击 '📸 获取截图'",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
                
        except Exception as e:
            logger.error(f"Screenshot command failed: {e}")
            await update.message.reply_text(f"❌ 失败: {str(e)}")

    async def _cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /config command."""
        if not self._check_authorization(update.effective_user.id):
            await update.message.reply_text("❌ 未授权的用户")
            return

        if len(context.args) < 2:
            # Show config menu
            keyboard = [
                [
                    InlineKeyboardButton("🧩 复杂任务", callback_data="config_complex"),
                    InlineKeyboardButton("📧 邮件通知", callback_data="config_email"),
                ],
                [
                    InlineKeyboardButton("🐛 调试模式", callback_data="config_debug"),
                ],
                [InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("⚙️ **配置选项**", reply_markup=reply_markup, parse_mode='Markdown')
            return

        # Handle text config command
        option = context.args[0].lower()
        value = context.args[1].lower() in ['on', 'true', '1', 'yes']

        try:
            from web_app.routers.telegram import load_telegram_config, save_telegram_config
            
            config = load_telegram_config()
            
            # Update config based on option
            if option == "complex":
                config['complex_mode'] = value
                msg = f"{'✅ 已开启' if value else '❌ 已关闭'} 复杂任务模式"
            elif option == "email":
                config['email_notifications'] = value
                msg = f"{'✅ 已开启' if value else '❌ 已关闭'} 邮件通知"
            elif option == "debug":
                config['debug_mode'] = value
                msg = f"{'✅ 已开启' if value else '❌ 已关闭'} 调试模式"
            else:
                await update.message.reply_text(f"❌ 未知选项: {option}")
                return
            
            save_telegram_config(config)
            await update.message.reply_text(msg)
            
        except Exception as e:
            logger.error(f"Config update failed: {e}")
            await update.message.reply_text(f"❌ 配置失败: {str(e)}")

    async def _button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()

        if not self._check_authorization(update.effective_user.id):
            await query.edit_message_text("❌ 未授权的用户")
            return

        try:
            callback_data = query.data
            # Use chat_id to support both private and group chats
            chat_id = str(query.message.chat_id)
            
            # Handle main menu - Show new comprehensive menu
            if callback_data == "main_menu":
                await self._show_main_menu(query, is_query=True)
                
                # Clean up pending actions
                if chat_id in self._pending_tasks:
                    del self._pending_tasks[chat_id]
                if chat_id in self._selected_devices:
                    del self._selected_devices[chat_id]
                if chat_id in self._pending_action:
                    del self._pending_action[chat_id]
                    
                return
            
            # === NEW MENU SYSTEM ROUTING ===
            # Category menus
            if callback_data == "menu_tasks":
                await self._show_tasks_menu(query)
                return
            if callback_data == "menu_devices":
                await self._show_devices_menu(query)
                return
            if callback_data == "menu_settings":
                await self._show_settings_menu(query)
                return
            if callback_data == "menu_models":
                await self._show_models_menu(query)
                return
            if callback_data == "menu_advanced":
                await self._show_advanced_menu(query)
                return
            if callback_data == "menu_help":
                await self._show_help_menu(query)
                return
            
            
            # === TASK EXECUTION ===
            if callback_data == "get_task":
                # Prompt user to input task via message
                await query.edit_message_text(
                    "📝 **请输入任务内容**\n\n"
                    "💡 描述您想要设备执行的任务\n"
                    "例如：打开微信，给张三发送消息\n\n"
                    "⏳ 等待您的输入...",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")
                    ]]),
                    parse_mode='Markdown'
                )
                # Mark as task action so we know what to do when user sends message
                self._pending_action[chat_id] = "task"
                return
            
            # === MODEL CONFIGURATION FEATURES ===
            if callback_data == "models_select":
                await self._show_model_selection(query)
                return
            
            if callback_data == "models_params":
                await self._show_model_params(query)
                return
            
            if callback_data == "models_api":
                await self._show_api_keys(query)
                return
            
            # Handle model activation
            if callback_data.startswith("activate_model_"):
                from web_app.services.model_service import model_service
                
                service_id = callback_data.replace("activate_model_", "")
                success = model_service.activate_service(service_id)
                
                if success:
                    # Refresh model selection display
                    await self._show_model_selection(query)
                else:
                    await query.answer("❌ 切换模型失败", show_alert=True)
                return
            
            # Handle parameter adjustments
            if callback_data.startswith("param_"):
                await self._handle_param_adjustment(query, callback_data)
                return
            
            # Test API connection
            if callback_data.startswith("test_api_"):
                await self._handle_test_api(query, callback_data)
                return
            # === END MODEL CONFIGURATION ===
            
            # === SCHEDULED TASKS FEATURES ===
            if callback_data == "tasks_scheduled":
                await self._show_scheduled_tasks(query)
                return
            
            # Handle task toggle (enable/disable)
            if callback_data.startswith("toggle_task_"):
                await self._handle_toggle_task(query, callback_data)
                return
            
            # Handle task delete
            if callback_data.startswith("delete_task_"):
                await self._handle_delete_task(query, callback_data)
                return
            # === END SCHEDULED TASKS ===
            
            # === EMAIL SETTINGS FEATURES ===
            if callback_data == "settings_email":
                await self._show_email_settings(query)
                return
            
            # Handle test email
            if callback_data == "test_email":
                await self._handle_test_email(query)
                return
            # === END EMAIL SETTINGS ===
            
            # === DIAGNOSTIC FEATURES ===
            if callback_data == "advanced_diagnostic":
                await self._show_system_diagnostic(query)
                return
            
            # Refresh diagnostic
            if callback_data == "refresh_diagnostic":
                await self._show_system_diagnostic(query)
                return
            # === END DIAGNOSTIC ===
            
            # === DEVICE UNLOCK CONFIG ===
            if callback_data == "devices_unlock":
                await self._show_device_unlock_config(query)
                return
            # === END DEVICE UNLOCK ===
            
            # === TASK HISTORY ===
            if callback_data == "tasks_history":
                await self._show_task_history(query)
                return
            # === END TASK HISTORY ===
            
            # === DEVICE APPS ===
            if callback_data == "devices_apps":
                await self._show_device_apps(query)
                return
            # === END DEVICE APPS ===
            
            # === RULES CONFIG ===
            if callback_data == "advanced_rules":
                await self._show_rules_config(query)
                return
            # === END RULES ===
            
            # === REMAINING FEATURES ===
            if callback_data == "tasks_chat":
                await self._show_chat_history(query)
                return
            
            if callback_data == "advanced_stats":
                await self._show_statistics(query)
                return
            
            if callback_data in ["help_guide", "help_quickstart", "help_feedback", "help_changelog"]:
                await self._show_help_section(query, callback_data)
                return
            
            if callback_data in ["devices_add", "devices_files", "settings_telegram", "settings_logs", "settings_ui"]:
                await self._show_web_guidance(query, callback_data)
                return
            # === END REMAINING ===
            
            # Feature stubs
            stub_mappings = {
                # tasks_scheduled is now implemented
                # tasks_history is now implemented
                "tasks_chat": "Chat 对话历史",
                "devices_add": "添加设备",
                # devices_unlock is now implemented
                # devices_apps is now implemented
                "devices_files": "文件管理",
                # settings_email is now implemented
                "settings_telegram": "Telegram 权限管理",
                "settings_logs": "日志设置",
                "settings_ui": "UI 设置",
                # models_select is now implemented
                # models_params is now implemented
                # models_api is now implemented
                # advanced_rules is now implemented
                # advanced_diagnostic is now implemented
                "advanced_stats": "统计信息",
                "help_guide": "使用指南",
                "help_quickstart": "快速开始",
                "help_feedback": "问题反馈",
                "help_changelog": "更新日志"
            }
            
            if callback_data in stub_mappings:
                await self._handle_feature_stub(query, stub_mappings[callback_data])
                return
            # === END NEW MENU SYSTEM ROUTING ===
            
            # Handle device selection
            if callback_data.startswith("select_device_"):
                from web_app.services.device_service import device_service
                
                device_id = callback_data.replace("select_device_", "")
                
                # Toggle device selection
                if chat_id not in self._selected_devices:
                    self._selected_devices[chat_id] = set()
                
                if device_id in self._selected_devices[chat_id]:
                    self._selected_devices[chat_id].remove(device_id)
                else:
                    self._selected_devices[chat_id].add(device_id)
                
                # Update button display
                devices = device_service.get_all_devices()
                keyboard = []
                for device in devices:
                    status_emoji = "🟢" if device.status == "online" else "🔴"
                    device_label = f"{status_emoji} {device.id[:12]}..."
                    if device.name:
                        device_label = f"{status_emoji} {device.name[:15]}"
                    
                    # Add checkmark if selected
                    if device.id in self._selected_devices[chat_id]:
                        device_label = "✓ " + device_label
                    
                    keyboard.append([InlineKeyboardButton(
                        device_label,
                        callback_data=f"select_device_{device.id}"
                    )])
                
                keyboard.append([
                    InlineKeyboardButton("✅ 全选", callback_data="select_all_devices"),
                    InlineKeyboardButton("🔄 清除", callback_data="clear_devices"),
                ])
                
                # Add action button based on pending action
                action = self._pending_action.get(chat_id, "task")
                logger.info(f"Device selection update - chat_id: {chat_id}, action: {action}, devices: {len(self._selected_devices[chat_id])}")
                if action == "screenshot":
                    keyboard.append([InlineKeyboardButton("📸 获取截图", callback_data="execute_screenshot")])
                else:
                    keyboard.append([InlineKeyboardButton("▶️ 执行任务", callback_data="execute_task")])
                    
                keyboard.append([InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                task_content = self._pending_tasks.get(chat_id, "未知任务")
                
                # Escape markdown special characters in task content
                task_content_safe = task_content.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
                
                await query.edit_message_text(
                    f"📝 **任务:** {task_content_safe}\n\n"
                    f"📱 已选择 {len(self._selected_devices[chat_id])} 个设备\n"
                    f"💡 点击设备切换选择状态",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            
            elif callback_data == "select_all_devices":
                from web_app.services.device_service import device_service
                
                devices = device_service.get_all_devices()
                self._selected_devices[chat_id] = {d.id for d in devices}
                
                # Update display
                keyboard = []
                for device in devices:
                    status_emoji = "🟢" if device.status == "online" else "🔴"
                    device_label = f"{status_emoji} {device.id[:12]}..."
                    if device.name:
                        device_label = f"{status_emoji} {device.name[:15]}"
                    device_label = "✓ " + device_label
                    
                    keyboard.append([InlineKeyboardButton(
                        device_label,
                        callback_data=f"select_device_{device.id}"
                    )])
                
                keyboard.append([
                    InlineKeyboardButton("✅ 全选", callback_data="select_all_devices"),
                    InlineKeyboardButton("🔄 清除", callback_data="clear_devices"),
                ])
                
                # Add action button based on pending action
                action = self._pending_action.get(chat_id, "task")
                logger.info(f"Select ALL - chat_id: {chat_id}, action: {action}")
                if action == "screenshot":
                    keyboard.append([InlineKeyboardButton("📸 获取截图", callback_data="execute_screenshot")])
                else:
                    keyboard.append([InlineKeyboardButton("▶️ 执行任务", callback_data="execute_task")])
                    
                keyboard.append([InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                task_content = self._pending_tasks.get(chat_id, "未知任务")
                
                # Escape markdown special characters
                task_content_safe = task_content.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
                
                await query.edit_message_text(
                    f"📝 **任务:** {task_content_safe}\n\n"
                    f"📱 已选择 {len(self._selected_devices[chat_id])} 个设备 (全部)\n"
                    f"💡 点击设备取消选择",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            
            elif callback_data == "clear_devices":
                self._selected_devices[chat_id] = set()
                
                from web_app.services.device_service import device_service
                devices = device_service.get_all_devices()
                
                keyboard = []
                for device in devices:
                    status_emoji = "🟢" if device.status == "online" else "🔴"
                    device_label = f"{status_emoji} {device.id[:12]}..."
                    if device.name:
                        device_label = f"{status_emoji} {device.name[:15]}"
                    
                    keyboard.append([InlineKeyboardButton(
                        device_label,
                        callback_data=f"select_device_{device.id}"
                    )])
                
                keyboard.append([
                    InlineKeyboardButton("✅ 全选", callback_data="select_all_devices"),
                    InlineKeyboardButton("🔄 清除", callback_data="clear_devices"),
                ])
                
                # Add action button based on pending action
                action = self._pending_action.get(chat_id, "task")
                logger.info(f"Clear devices - chat_id: {chat_id}, action: {action}")
                if action == "screenshot":
                    keyboard.append([InlineKeyboardButton("📸 获取截图", callback_data="execute_screenshot")])
                else:
                    keyboard.append([InlineKeyboardButton("▶️ 执行任务", callback_data="execute_task")])
                    
                keyboard.append([InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                task_content = self._pending_tasks.get(chat_id, "未知任务")
                
                # Escape markdown special characters
                task_content_safe = task_content.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
                
                await query.edit_message_text(
                    f"📝 **任务:** {task_content_safe}\n\n"
                    f"📱 未选择设备\n"
                    f"💡 点击设备进行选择",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            
            elif callback_data == "execute_task":
                #  Instead of executing immediately, show task options page
                selected_devices = self._selected_devices.get(chat_id, set())
                
                if not selected_devices:
                    await query.answer("❌ 请至少选择一个设备", show_alert=True)
                    return
                
                # Initialize task options if not exists (both default to False)
                if chat_id not in self._task_options:
                    self._task_options[chat_id] = {"complex_task": False, "send_email": False}
                
                await self._show_task_options(query, chat_id)
                return
            
            # Handle task option toggles
            elif callback_data == "toggle_complex_task":
                if chat_id not in self._task_options:
                    self._task_options[chat_id] = {"complex_task": False, "send_email": False}
                self._task_options[chat_id]["complex_task"] = not self._task_options[chat_id]["complex_task"]
                await self._show_task_options(query, chat_id)
                return
            
            elif callback_data == "toggle_send_email":
                if chat_id not in self._task_options:
                    self._task_options[chat_id] = {"complex_task": False, "send_email": False}
                self._task_options[chat_id]["send_email"] = not self._task_options[chat_id]["send_email"]
                await self._show_task_options(query, chat_id)
                return
            
            elif callback_data == "confirm_task_options":
                # Proceed to actual task execution with selected options
                task_content = self._pending_tasks.get(chat_id)
                selected_devices = self._selected_devices.get(chat_id, set())
                task_options = self._task_options.get(chat_id, {"complex_task": False, "send_email": False})
                
                if not task_content:
                    await query.edit_message_text("❌ 任务已过期，请重新提交")
                    return
                
                if not selected_devices:
                    await query.answer("❌ 请至少选择一个设备", show_alert=True)
                    return
                
                # Execute task
                from web_app.services.task_service import task_service
                import base64
                from io import BytesIO
                
                options_text = ""
                if task_options["complex_task"]:
                    options_text += "🔓 保持解锁 "
                if task_options["send_email"]:
                    options_text += "📧 邮件通知 "
                
                await query.edit_message_text(
                    f"📝 **任务执行中**\n\n"
                    f"🎯 {task_content}\n"
                    f"📱 设备: {len(selected_devices)} 个\n"
                    f"⚙️ 选项: {options_text or '无'}\n\n"
                    f"⏳ 请稍候...",
                    parse_mode='Markdown'
                )
                
                try:
                    # Execute task and get result directly from return value
                    task_result = await task_service.run_task(
                        task_content=task_content,
                        device_ids=list(selected_devices),
                        send_email=task_options["send_email"],
                        no_auto_lock=task_options["complex_task"],  # Use no_auto_lock for complex task mode
                        task_type="manual"
                    )
                    
                    logger.info(f"Task execution completed - task_result exists: {task_result is not None}, status: {task_result.status if task_result else 'None'}")
                    
                    if task_result:
                        status_emoji = "✅" if task_result.status == "completed" else "❌"
                        # Escape task content for markdown
                        task_content_safe = self._escape_markdown(task_content)
                        response = f"{status_emoji} **任务{task_result.status}**\n\n"
                        response += f"🎯 {task_content_safe}\n"
                        response += f"⏱️ 进度: {task_result.progress}%"
                        
                        # Send status with main menu button
                        keyboard = [[InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await self._application.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=response,
                            reply_markup=reply_markup,
                            parse_mode='Markdown'
                        )
                        
                        # Send logs
                        logger.info(f"Task logs count: {len(task_result.logs) if task_result.logs else 0}")
                        if task_result.logs and len(task_result.logs) > 0:
                            logs_text = "\n".join(task_result.logs[-15:])
                            if len(logs_text) > 3500:
                                logs_text = logs_text[-3500:]
                            await self._application.bot.send_message(
                                chat_id=query.message.chat_id,
                                text=f"📋 **日志摘要**\n```\n{logs_text}\n```",
                                parse_mode='Markdown'
                            )
                        
                        # Send screenshot
                        config = self._config
                        screenshot_data = getattr(task_result, '_screenshot_data', None)
                        logger.info(f"Screenshot config: {config.get('send_screenshots', True)}, data exists: {screenshot_data is not None}")
                        if config.get('send_screenshots', True) and screenshot_data:
                            try:
                                if isinstance(screenshot_data, str):
                                    screenshot_bytes = base64.b64decode(screenshot_data)
                                else:
                                    screenshot_bytes = screenshot_data
                                
                                await self._application.bot.send_photo(
                                    chat_id=query.message.chat_id,
                                    photo=BytesIO(screenshot_bytes),
                                    caption=f"📸 任务完成截图\n🎯 {task_content_safe}"
                                )
                            except Exception as e:
                                logger.error(f"Failed to send screenshot: {e}")
                        
                        # Delete the progress message
                        await query.delete_message()
                        
                        # Send final completion message with main menu button at the end
                        keyboard = [[InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await self._application.bot.send_message(
                            chat_id=query.message.chat_id,
                            text="✅ 任务已完成，结果已发送",
                            reply_markup=reply_markup
                        )
                    else:
                        logger.warning("Task completed but task_result is None!")
                        await query.edit_message_text("✅ 任务已提交")
                        
                except Exception as e:
                    logger.error(f"Task execution failed: {e}")
                    await query.edit_message_text(f"❌ 执行失败: {str(e)}")
                
                # Clean up
                if chat_id in self._pending_tasks:
                    del self._pending_tasks[chat_id]
                if chat_id in self._selected_devices:
                    del self._selected_devices[chat_id]
                if chat_id in self._pending_action:
                    del self._pending_action[chat_id]
                
                return
            
            elif callback_data == "execute_screenshot":
                selected_devices = self._selected_devices.get(chat_id, set())
                
                if not selected_devices:
                    await query.answer("❌ 请至少选择一个设备", show_alert=True)
                    return
                
                # Get screenshots
                from web_app.services.device_service import device_service
                import base64
                from io import BytesIO
                
                await query.edit_message_text(
                    f"📸 **获取截图中**\n\n"
                    f"📱 设备: {len(selected_devices)} 个\n\n"
                    f"⏳ 请稍候...",
                    parse_mode='Markdown'
                )
                
                success_count = 0
                try:
                    for device_id in selected_devices:
                        # Track original lock state for this device
                        was_locked = False
                        try:
                            # Check if device is locked
                            was_locked = await device_service.is_screen_locked(device_id)
                            logger.info(f"Device {device_id} lock state before screenshot: {was_locked}")
                            
                            # Unlock if needed
                            if was_locked:
                                pin = device_service.get_device_pin(device_id)
                                unlock_success = await device_service.unlock_device(device_id, pin)
                                if not unlock_success:
                                    logger.warning(f"Failed to unlock device {device_id} for screenshot")
                                    continue  # Skip this device if unlock failed
                                logger.info(f"Unlocked device {device_id} for screenshot")
                            
                            # Capture screenshot
                            screenshot_data = await device_service.get_screenshot(device_id)
                            
                            if screenshot_data:
                                if isinstance(screenshot_data, str):
                                    screenshot_bytes = base64.b64decode(screenshot_data)
                                else:
                                    screenshot_bytes = screenshot_data
                                
                                await self._application.bot.send_photo(
                                    chat_id=query.message.chat_id,
                                    photo=BytesIO(screenshot_bytes),
                                    caption=f"📱 设备: {self._escape_markdown(device_id)}"
                                )
                                success_count += 1
                        except Exception as e:
                            logger.error(f"Failed to get screenshot from {device_id}: {e}")
                        finally:
                            # Restore lock state if it was originally locked
                            if was_locked:
                                try:
                                    await device_service.lock_device(device_id)
                                    logger.info(f"Restored lock state for device {device_id}")
                                except Exception as e:
                                    logger.error(f"Failed to restore lock state for {device_id}: {e}")
                    
                    # Delete the progress message
                    await query.delete_message()
                    
                    # Send final completion message with main menu button
                    keyboard = [[InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await self._application.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"✅ **截图完成**\n\n📸 成功: {success_count}/{len(selected_devices)} 个设备",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Screenshot execution failed: {e}")
                    await query.edit_message_text(f"❌ 执行失败: {str(e)}")
                
                # Clean up
                if chat_id in self._selected_devices:
                    del self._selected_devices[chat_id]
                if chat_id in self._pending_action:
                    del self._pending_action[chat_id]
                
                return
            
            # Handle quick action buttons
            if callback_data == "show_help":
                help_text = """
📚 **命令帮助**

**任务控制：**
`/task <指令>` - 执行手机自动化任务
   示例：/task 打开微信

**状态查询：**
`/status` - 查看当前任务状态
`/devices` - 列出所有连接的设备
`/screenshot` - 获取当前设备截图

**配置选项：**
`/config` - 打开配置菜单
"""
                # Add main menu button
                keyboard = [[InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
                return
                
            elif callback_data == "show_devices":
                from web_app.services.device_service import device_service
                devices = device_service.get_all_devices()
                
                if not devices:
                    await query.edit_message_text("📱 没有连接的设备")
                    return
                
                response = f"📱 **连接的设备** ({len(devices)})\n\n"
                for i, device in enumerate(devices, 1):
                    status_emoji = "🟢" if device.status == "online" else "🔴"
                    # Escape device ID for markdown
                    device_id_safe = device.id.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
                    response += f"{i}. {status_emoji} `{device_id_safe}`\n"
                    if device.name:
                        device_name_safe = device.name.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
                        response += f"   📱 {device_name_safe}\n"
                
                # Add main menu button
                keyboard = [[InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')
                return
                
            elif callback_data == "get_screenshot":
                # Show device selection for screenshot instead of getting immediately
                from web_app.services.device_service import device_service
                
                devices = device_service.get_all_devices()
                if not devices:
                    await query.edit_message_text("❌ 没有可用的设备")
                    return
                
                # Store action for this user
                self._pending_action[chat_id] = "screenshot"
                self._selected_devices[chat_id] = set()  # Reset selection
                
                # Create device selection buttons
                keyboard = []
                for device in devices:
                    status_emoji = "🟢" if device.status == "online" else "🔴"
                    device_label = f"{status_emoji} {device.id[:12]}..."
                    if device.name:
                        device_label = f"{status_emoji} {device.name[:15]}"
                    
                    keyboard.append([InlineKeyboardButton(
                        device_label,
                        callback_data=f"select_device_{device.id}"
                    )])
                
                # Add control buttons
                keyboard.append([
                    InlineKeyboardButton("✅ 全选", callback_data="select_all_devices"),
                    InlineKeyboardButton("🔄 清除", callback_data="clear_devices"),
                ])
                keyboard.append([
                    InlineKeyboardButton("📸 获取截图", callback_data="execute_screenshot"),
                ])
                keyboard.append([InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"📸 **获取截图**\n\n"
                    f"📱 请选择设备 (可多选):\n"
                    f"💡 选择后点击 '📸 获取截图'",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
                
            elif callback_data == "show_config":
                keyboard = [
                    [
                        InlineKeyboardButton("🧩 复杂任务", callback_data="config_complex"),
                        InlineKeyboardButton("📧 邮件通知", callback_data="config_email"),
                    ],
                    [
                        InlineKeyboardButton("🐛 调试模式", callback_data="config_debug"),
                    ],
                    [
                        InlineKeyboardButton("🏠 主菜单", callback_data="main_menu"),
                    ],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("⚙️ **配置选项**", reply_markup=reply_markup, parse_mode='Markdown')
                return
            
            # Handle config toggle buttons
            if callback_data.startswith("config_"):
                from web_app.routers.telegram import load_telegram_config, save_telegram_config
                
                config = load_telegram_config()
                option = callback_data.replace("config_", "")
                
                # Toggle the option
                key_map = {
                    "complex": "complex_mode",
                    "email": "email_notifications",
                    "debug": "debug_mode"
                }
                
                if option in key_map:
                    key = key_map[option]
                    current = config.get(key, False)
                    config[key] = not current
                    save_telegram_config(config)
                    
                    status = "✅ 已开启" if config[key] else "❌ 已关闭"
                    option_names = {
                        "complex": "复杂任务模式",
                        "email": "邮件通知",
                        "debug": "调试模式"
                    }
                    await query.edit_message_text(f"{status} {option_names[option]}")
                    
        except Exception as e:
            logger.error(f"Button callback failed: {e}")
            await query.edit_message_text(f"❌ 操作失败: {str(e)}")

    async def send_message(self, chat_id: int, text: str):
        """Send a message to a specific chat."""
        if not self._application or not self._running:
            logger.warning("Cannot send message: bot not running")
            return

        try:
            await self._application.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

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
🏠 **欢迎使用 AutoGLM Bot！**

🤖 您的智能手机自动化助手已就绪

✨ **核心能力：**
• 📋 自动化任务执行 - AI 驱动的智能操作
• 📱 多设备管理 - 统一控制所有设备
• ⚙️ 灵活配置 - 个性化定制您的体验
• 🤖 AI 模型集成 - GLM、Gemini 等主流模型

👇 **请选择功能分类：**
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
    
    # === MODEL CONFIGURATION FUNCTIONS ===
    async def _show_model_selection(self, query):
        """Show model selection menu with all available models."""
        from web_app.services.model_service import model_service
        
        # Get all models and active model
        services = model_service.get_all_services()
        active_service = model_service.get_active_service_dict()
        active_id = active_service['id'] if active_service else None
        
        text = """
🎯 **模型选择**

选择您想要使用的 AI 模型：
"""
        
        keyboard = []
        for service in services:
            service_id = service['id']
            service_name = service['name']
            model_name = service.get('model_name', '')
            
            # Mark active model with ✅
            if service_id == active_id:
                button_text = f"✅ {service_name}"
                if model_name:
                    button_text += f" ({model_name})"
            else:
                button_text = f"   {service_name}"
                if model_name:
                    button_text += f" ({model_name})"
            
            keyboard.append([
                InlineKeyboardButton(button_text, callback_data=f"activate_model_{service_id}")
            ])
        
        # Add back button
        self._add_back_button(keyboard, "menu_models")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_model_params(self, query):
        """Show model parameters configuration menu."""
        from web_app.services.model_service import model_service
        
        # Get active model
        active_service = model_service.get_active_service_dict()
        if not active_service:
            await query.answer("❌ 没有激活的模型", show_alert=True)
            return
        
        model_name = active_service.get('name', '未知模型')
        temperature = active_service.get('temperature', 0.0)
        max_tokens = active_service.get('max_tokens', 3000)
        top_p = active_service.get('top_p', 0.85)
        freq_penalty = active_service.get('frequency_penalty', 0.2)
        
        text = f"""
⚡ **模型参数配置**

当前模型: **{model_name}**

📊 **当前参数:**
• Temperature: `{temperature}` 
  (创造性: 越高越随机)
• Max Tokens: `{max_tokens}`
  (回答长度上限)
• Top P: `{top_p}`
  (采样多样性)
• Frequency Penalty: `{freq_penalty}`
  (重复惩罚)

点击下方按钮调整参数：
"""
        
        keyboard = [
            # Temperature row
            [InlineKeyboardButton(f"🌡️ Temperature", callback_data="param_info_temp")],
            [
                InlineKeyboardButton("0.3", callback_data="param_temp_0.3"),
                InlineKeyboardButton("0.5", callback_data="param_temp_0.5"),
                InlineKeyboardButton(f"✓ {temperature}" if temperature in [0.7] else "0.7", callback_data="param_temp_0.7"),
                InlineKeyboardButton("0.9", callback_data="param_temp_0.9"),
                InlineKeyboardButton("1.0", callback_data="param_temp_1.0"),
            ],
            # Max Tokens row
            [InlineKeyboardButton(f"📏 Max Tokens", callback_data="param_info_tokens")],
            [
                InlineKeyboardButton("1024", callback_data="param_tokens_1024"),
                InlineKeyboardButton(f"✓ {max_tokens}" if max_tokens in [2048, 3000] else "2048", callback_data="param_tokens_2048"),
                InlineKeyboardButton("4096", callback_data="param_tokens_4096"),
                InlineKeyboardButton("8192", callback_data="param_tokens_8192"),
            ],
        ]
        
        self._add_back_button(keyboard, "menu_models")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_param_adjustment(self, query, callback_data: str):
        """Handle model parameter adjustment."""
        from web_app.services.model_service import model_service
        
        # Get active model
        active_service = model_service.get_active_service_dict()
        if not active_service:
            await query.answer("❌ 没有激活的模型", show_alert=True)
            return
        
        # Parse callback data
        parts = callback_data.split("_")
        if len(parts) < 3:
            return
        
        param_type = parts[1]  # temp, tokens, etc.
        param_value = "_".join(parts[2:])  # value (might contain underscores)
        
        # Update the parameter
        updated = False
        try:
            if param_type == "temp":
                active_service['temperature'] = float(param_value)
                updated = True
            elif param_type == "tokens":
                active_service['max_tokens'] = int(param_value)
                updated = True
            
            if updated:
                # Save to model service
                success = model_service.update_service(active_service)
                if success:
                    # Refresh display
                    await self._show_model_params(query)
                else:
                    await query.answer("❌ 保存失败", show_alert=True)
        except Exception as e:
            logger.error(f"Parameter adjustment failed: {e}")
            await query.answer("❌ 参数更新失败", show_alert=True)
    
    async def _show_api_keys(self, query):
        """Show API key configuration status."""
        from web_app.services.model_service import model_service
        
        # Get all services
        services = model_service.get_all_services()
        
        text = """
🔑 **API 密钥管理**

以下是所有模型服务的 API 配置状态：

"""
        
        keyboard = []
        for service in services:
            service_id = service['id']
            service_name = service['name']
            api_key = service.get('api_key', '')
            base_url = service.get('base_url', '')
            
            # Check if API key is configured
            if api_key and len(api_key) > 0:
                # Mask the key for security
                if len(api_key) > 8:
                    masked_key = api_key[:4] + "..." + api_key[-4:]
                else:
                    masked_key = "***"
                status_icon = "✅"
                status_text = "已配置"
            else:
                masked_key = "未配置"
                status_icon = "❌"
                status_text = "未配置"
            
            text += f"""
**{service_name}** {status_icon}
• 状态: {status_text}
• API Key: `{masked_key}`
• Base URL: `{base_url}`

"""
            
            # Add test button if configured
            if api_key:
                keyboard.append([
                    InlineKeyboardButton(f"🧪 测试 {service_name}", callback_data=f"test_api_{service_id}")
                ])
        
        text += """
⚠️ **安全提示:**
为了安全，请在 Web 界面配置 API 密钥
不要在 Telegram 中直接发送密钥
"""
        
        self._add_back_button(keyboard, "menu_models")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_test_api(self, query, callback_data: str):
        """Test API connection for a model service."""
        from web_app.services.model_service import model_service
        import httpx
        
        service_id = callback_data.replace("test_api_", "")
        
        # Show testing message
        await query.answer("🧪 正在测试连接...", show_alert=False)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://localhost:8080/api/models/{service_id}/test",
                    timeout=30.0
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        await query.answer("✅ 连接测试成功！", show_alert=True)
                    else:
                        message = result.get('message', '未知错误')
                        await query.answer(f"❌ 测试失败：{message}", show_alert=True)
                else:
                    await query.answer("❌ 测试请求失败", show_alert=True)
        except Exception as e:
            logger.error(f"API test failed: {e}")
            await query.answer(f"❌ 测试失败：{str(e)}", show_alert=True)
    # === END MODEL CONFIGURATION ===
    
    # === SCHEDULED TASKS FUNCTIONS ===
    async def _show_scheduled_tasks(self, query):
        """Show list of scheduled tasks."""
        from web_app.services.scheduler_service import scheduler_service
        
        # Get all scheduled tasks
        tasks_data = scheduler_service.get_all_tasks_dict()
        
        if not tasks_data:
            text = """
📅 **定时任务列表**

暂无定时任务

💡 提示：您可以在 Web 界面创建定时任务
"""
            keyboard = []
            self._add_back_button(keyboard, "menu_tasks")
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        # Build task list
        text = f"""
📅 **定时任务列表** ({len(tasks_data)} 个任务)

"""
        
        keyboard = []
        for i, task in enumerate(tasks_data[:10], 1):  # Limit to 10 tasks
            task_id = task['id']
            task_name = task['name']
            enabled = task.get('enabled', True)
            schedule_type = task.get('schedule_type', 'daily')
            
            # Status icon
            status_icon = "✅" if enabled else "⏸️"
            
            # Schedule display
            if schedule_type == "daily":
                schedule = f"每天 {task.get('daily_time', '09:00')}"
            elif schedule_type == "weekly":
                days_map = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
                days = task.get('weekly_days', [0])
                day_str = "、".join([f"周{days_map.get(d, d)}" for d in days])
                schedule = f"{day_str} {task.get('weekly_time', '09:00')}"
            elif schedule_type == "interval":
                mins = task.get('interval_minutes', 60)
                schedule = f"每 {mins} 分钟"
            else:
                schedule = schedule_type
            
            # Add task info to text
            text += f"{i}️⃣ **{task_name}** {status_icon}\n   ⏰ {schedule}\n\n"
            
            # Add control buttons for each task
            toggle_text = "禁用" if enabled else "启用"
            keyboard.append([
                InlineKeyboardButton(f"{toggle_text}", callback_data=f"toggle_task_{task_id}"),
                InlineKeyboardButton("🗑️ 删除", callback_data=f"delete_task_{task_id}"),
            ])
        
        self._add_back_button(keyboard, "menu_tasks")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_toggle_task(self, query, callback_data: str):
        """Toggle a scheduled task enabled/disabled."""
        from web_app.services.scheduler_service import scheduler_service
        import httpx
        
        task_id = callback_data.replace("toggle_task_", "")
        
        # Get task to check current status
        task = scheduler_service.get_task(task_id)
        if not task:
            await query.answer("❌ 任务不存在", show_alert=True)
            return
        
        # Toggle the status
        new_status = not task.enabled
        
        # Update via API
        try:
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    f"http://localhost:8080/api/scheduler/tasks/{task_id}/toggle",
                    json={"enabled": new_status},
                    timeout=10.0
                )
                if response.status_code == 200:
                    # Refresh the task list
                    await self._show_scheduled_tasks(query)
                else:
                    await query.answer("❌ 更新失败", show_alert=True)
        except Exception as e:
            logger.error(f"Toggle task failed: {e}")
            await query.answer("❌ 操作失败", show_alert=True)
    
    async def _handle_delete_task(self, query, callback_data: str):
        """Delete a scheduled task."""
        from web_app.services.scheduler_service import scheduler_service
        import httpx
        
        task_id = callback_data.replace("delete_task_", "")
        
        # Delete via API
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"http://localhost:8080/api/scheduler/tasks/{task_id}",
                    timeout=10.0
                )
                if response.status_code == 200:
                    # Refresh the task list
                    await self._show_scheduled_tasks(query)
                else:
                    await query.answer("❌ 删除失败", show_alert=True)
        except Exception as e:
            logger.error(f"Delete task failed: {e}")
            await query.answer("❌ 操作失败", show_alert=True)
    # === END SCHEDULED TASKS ===
    
    # === EMAIL SETTINGS FUNCTIONS ===
    async def _show_email_settings(self, query):
        """Show email notification settings."""
        import httpx
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:8080/api/settings/email",
                    timeout=10.0
                )
                if response.status_code != 200:
                    await query.answer("❌ 获取邮件配置失败", show_alert=True)
                    return
                
                config = response.json()
        except Exception as e:
            logger.error(f"Failed to get email config: {e}")
            await query.answer("❌ 获取配置失败", show_alert=True)
            return
        
        # Check if email is configured
        enabled = config.get('enabled', False)
        smtp_server = config.get('smtp_server', '')
        smtp_port = config.get('smtp_port', 465)
        sender_email = config.get('sender_email', '')
        recipient_emails = config.get('recipient_emails', '')
        use_ssl = config.get('use_ssl', True)
        
        if smtp_server and sender_email:
            status_icon = "✅"
            status_text = "已配置" if enabled else "已配置（未启用）"
        else:
            status_icon = "❌"
            status_text = "未配置"
        
        text = f"""
📧 **邮件通知设置**

**配置状态:** {status_icon} {status_text}

**SMTP 服务器:**
• 服务器: `{smtp_server or '未设置'}`
• 端口: `{smtp_port}`
• SSL: `{'是' if use_ssl else '否'}`

**发件人:** `{sender_email or '未设置'}`
**密码:** `{'***' if config.get('sender_password') else '未设置'}`

**收件人:** `{recipient_emails or '未设置'}`

**通知开关:** `{'✅ 已启用' if enabled else '⏸️ 已禁用'}`

⚠️ **配置提示:**
完整的邮件配置需要在 Web 界面进行
"""
        
        keyboard = []
        
        # Add test button if configured
        if smtp_server and sender_email:
            keyboard.append([
                InlineKeyboardButton("🧪 测试邮件连接", callback_data="test_email")
            ])
        
        self._add_back_button(keyboard, "menu_settings")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_test_email(self, query):
        """Test email connection by sending a test email."""
        import httpx
        
        # Show testing message
        await query.answer("🧪 正在发送测试邮件...", show_alert=False)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8080/api/settings/email/test",
                    timeout=30.0
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        await query.answer("✅ 测试邮件发送成功！请检查收件箱", show_alert=True)
                    else:
                        message = result.get('message', '未知错误')
                        await query.answer(f"❌ 发送失败：{message}", show_alert=True)
                else:
                    await query.answer("❌ 测试请求失败", show_alert=True)
        except Exception as e:
            logger.error(f"Email test failed: {e}")
            await query.answer(f"❌ 测试失败：{str(e)}", show_alert=True)
    # === END EMAIL SETTINGS ===
    
    # === DIAGNOSTIC FUNCTIONS ===
    async def _show_system_diagnostic(self, query):
        """Show system diagnostic and health check information."""
        from web_app.services.device_service import device_service
        from web_app.services.scheduler_service import scheduler_service
        from web_app.services.model_service import model_service
        from datetime import datetime
        import httpx
        
        # Get device info
        devices = device_service.get_all_devices()
        device_count = len(devices)
        connected_devices = [d for d in devices if d.status == "connected"]
        connected_count = len(connected_devices)
        
        # Get scheduler info
        all_tasks = scheduler_service.get_all_tasks_dict()
        total_tasks = len(all_tasks)
        enabled_tasks = sum(1 for t in all_tasks if t.get('enabled', True))
        
        # Get model info
        try:
            active_model = model_service.get_active_service_dict()
            model_name = active_model.get('name', '未配置') if active_model else '未配置'
        except:
            model_name = '未知'
        
        # Get email status
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:8080/api/settings/email",
                    timeout=5.0
                )
                if response.status_code == 200:
                    email_config = response.json()
                    email_configured = bool(email_config.get('smtp_server') and email_config.get('sender_email'))
                    email_enabled = email_config.get('enabled', False)
                else:
                    email_configured = False
                    email_enabled = False
        except:
            email_configured = False
            email_enabled = False
        
        # Build diagnostic report
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        text = f"""
🏥 **系统诊断报告**

📅 **检查时间:** `{current_time}`

---

📱 **设备状态**
• 总设备数: `{device_count}`
• 在线设备: `{connected_count}` {'✅' if connected_count > 0 else '⚠️'}
• 离线设备: `{device_count - connected_count}`

📅 **定时任务**
• 总任务数: `{total_tasks}`
• 已启用: `{enabled_tasks}` {'✅' if enabled_tasks > 0 else '⏸️'}
• 已禁用: `{total_tasks - enabled_tasks}`

🤖 **AI 模型**
• 当前模型: `{model_name}` {'✅' if model_name != '未配置' else '❌'}

📧 **邮件通知**
• 配置状态: {'✅ 已配置' if email_configured else '❌ 未配置'}
• 通知开关: {'✅ 已启用' if email_enabled else '⏸️ 已禁用'}

---

**系统状态:** {'✅ 正常运行' if connected_count > 0 else '⚠️ 无可用设备'}

💡 **提示:** 点击刷新按钮更新诊断信息
"""
        
        keyboard = [
            [InlineKeyboardButton("🔄 刷新", callback_data="refresh_diagnostic")]
        ]
        
        self._add_back_button(keyboard, "menu_advanced")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    # === END DIAGNOSTIC ===
    
    # === DEVICE UNLOCK CONFIG ===
    async def _show_task_options(self, query, chat_id: str):
        """Show task execution options configuration page."""
        task_options = self._task_options.get(chat_id, {"complex_task": False, "send_email": False})
        task_content = self._pending_tasks.get(chat_id, "未知任务")
        selected_devices = self._selected_devices.get(chat_id, set())
        
        # Build toggle buttons with checkboxes
        keep_unlocked_icon = "☑️" if task_options["complex_task"] else "☐"
        email_icon = "☑️" if task_options["send_email"] else "☐"
        
        task_escaped = self._escape_markdown(task_content[:100])
        
        text = f"""
⚙️ **任务选项配置**

📝 **任务:** {task_escaped}
📱 **设备:** {len(selected_devices)} 个

**请选择任务选项:**

{keep_unlocked_icon} **保持解锁**
├ 任务执行后不自动锁屏
├ 适合连续执行多个任务
└ 完成后需手动锁定设备

{email_icon} **邮件通知**
├ 任务完成后发送邮件通知
├ 需先配置邮件设置
└ 包含任务结果和截图

💡 点击按钮切换开关状态
"""
        
        keyboard = [
            [InlineKeyboardButton(f"{keep_unlocked_icon} 保持解锁", callback_data="toggle_complex_task")],
            [InlineKeyboardButton(f"{email_icon} 邮件通知", callback_data="toggle_send_email")],
            [InlineKeyboardButton("✅ 确认并执行", callback_data="confirm_task_options")],
            [InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_device_unlock_config(self, query):
        """Show device unlock PIN configuration."""
        from web_app.services.device_service import device_service
        
        # Get all devices
        devices = device_service.get_all_devices()
        
        if not devices:
            text = """
🔓 **设备解锁配置**

暂无设备

💡 提示：请先连接设备
"""
            keyboard = []
            self._add_back_button(keyboard, "menu_devices")
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        text = f"""
🔓 **设备解锁配置**

以下是所有设备的 PIN 配置状态：

"""
        
        keyboard = []
        configured_count = 0
        
        for device in devices:
            device_id = device.id
            device_name = self._escape_markdown(device.name or device_id)
            
            # Get PIN status
            pin = device_service.get_device_pin(device_id)
            
            if pin:
                # Mask PIN for security
                masked_pin = "*" * len(pin)
                status_icon = "✅"
                status_text = "已配置"
                configured_count += 1
            else:
                masked_pin = "未配置"
                status_icon = "❌"
                status_text = "未配置"
            
            text += f"""
**{device_name}** {status_icon}
• 状态: {status_text}
• PIN: `{masked_pin}`

"""
        
        text += f"""
📊 **统计:** {configured_count}/{len(devices)} 设备已配置 PIN

⚠️ **配置说明:**
1. PIN 用于自动解锁设备屏幕
2. 完整的 PIN 配置需要在 Web 界面进行
3. PIN 信息仅存储在本地，不会上传
4. 截图功能会自动使用 PIN 解锁设备

💡 **安全提示:**
为了安全，请不要在 Telegram 中直接发送 PIN
"""
        
        self._add_back_button(keyboard, "menu_devices")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    # === END DEVICE UNLOCK ===
    
    # === TASK HISTORY ===
    async def _show_task_history(self, query):
        """Show task execution history and logs."""
        import httpx
        from datetime import datetime
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:8080/api/scheduler/logs?limit=10",
                    timeout=10.0
                )
                if response.status_code != 200:
                    await query.answer("❌ 获取任务历史失败", show_alert=True)
                    return
                
                data = response.json()
                logs = data.get('logs', [])
        except Exception as e:
            logger.error(f"Failed to get task history: {e}")
            await query.answer("❌ 获取历史失败", show_alert=True)
            return
        
        if not logs:
            text = """
📜 **任务执行历史**

暂无执行记录

💡 提示：执行定时任务后将显示历史记录
"""
        else:
            text = f"""
📜 **任务执行历史** (最近 {len(logs)} 条)

"""
            for i, log in enumerate(logs[:10], 1):
                task_name = log.get('task_name', '未知任务')
                success = log.get('success', False)
                message = log.get('message', '')
                timestamp = log.get('timestamp', '')
                
                # Format timestamp
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime("%m-%d %H:%M")
                except:
                    time_str = timestamp[:16] if len(timestamp) > 16 else timestamp
                
                status_icon = "✅" if success else "❌"
                
                text += f"""
{i}. **{self._escape_markdown(task_name)}** {status_icon}
   ⏰ {time_str}
   📝 {self._escape_markdown(message[:50])}

"""
        
        keyboard = []
        self._add_back_button(keyboard, "menu_tasks")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    # === END TASK HISTORY ===
    
    # === DEVICE APPS ===
    async def _show_device_apps(self, query):
        """Show installed applications on device."""
        from web_app.services.device_service import device_service
        
        devices = device_service.get_all_devices()
        if not devices:
            text = """
📱 **应用管理**

暂无设备

💡 提示：请先连接设备
"""
            keyboard = []
            self._add_back_button(keyboard, "menu_devices")
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        # Use first connected device
        device = devices[0]
        device_name = self._escape_markdown(device.name or device.id)
        
        text = f"""
📱 **应用管理**

设备: **{device_name}**

⚙️ **功能说明:**
• 查看已安装应用需要在 Web 界面进行
• Web 界面提供完整的应用列表
• 支持查看应用包名、版本等详细信息

💡 **提示:**
通过 Web 界面可以：
1. 查看所有已安装应用
2. 查看应用详细信息
3. 管理应用权限
"""
        
        keyboard = []
        self._add_back_button(keyboard, "menu_devices")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    # === END DEVICE APPS ===
    
    # === RULES CONFIG ===
    async def _show_rules_config(self, query):
        """Show automation rules configuration summary."""
        import httpx
        
        try:
            # Get app mappings count
            async with httpx.AsyncClient() as client:
                apps_response = await client.get(
                    "http://localhost:8080/api/rules/apps",
                    timeout=5.0
                )
                if apps_response.status_code == 200:
                    apps_data = apps_response.json()
                    total_apps = len(apps_data.get('apps', []))
                    custom_apps = sum(1 for app in apps_data.get('apps', []) if app.get('is_custom', False))
                else:
                    total_apps = 0
                    custom_apps = 0
                
                # Get action rules count
                actions_response = await client.get(
                    "http://localhost:8080/api/rules/actions",
                    timeout=5.0
                )
                if actions_response.status_code == 200:
                    actions_data = actions_response.json()
                    total_rules = sum(len(action.get('rules', [])) for action in actions_data.get('actions', []))
                    enabled_rules = sum(
                        sum(1 for rule in action.get('rules', []) if rule.get('enabled', True))
                        for action in actions_data.get('actions', [])
                    )
                else:
                    total_rules = 0
                    enabled_rules = 0
        except Exception as e:
            logger.error(f"Failed to get rules config: {e}")
            total_apps = 0
            custom_apps = 0
            total_rules = 0
            enabled_rules = 0
        
        text = f"""
⚙️ **规则配置总览**

📊 **应用映射**
• 总应用数: `{total_apps}`
• 自定义应用: `{custom_apps}`
• 系统预设: `{total_apps - custom_apps}`

🎯 **动作规则**
• 总规则数: `{total_rules}`
• 已启用: `{enabled_rules}` {'✅' if enabled_rules > 0 else '⏸️'}
• 已禁用: `{total_rules - enabled_rules}`

💡 **功能说明:**
规则系统控制 AI 如何执行任务：
• 应用映射：将应用名称映射到包名
• 动作规则：定义任务执行的条件和动作
• 时间配置：控制操作的等待时间

⚙️ **管理提示:**
完整的规则配置需要在 Web 界面进行
"""
        
        keyboard = []
        self._add_back_button(keyboard, "menu_advanced")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    # === END RULES ===
    
    # === REMAINING FEATURES ===
    async def _show_chat_history(self, query):
        """Show chat conversation history."""
        import httpx
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:8080/api/chat/sessions?limit=10",
                    timeout=10.0
                )
                if response.status_code != 200:
                    await query.answer("❌ 获取对话历史失败", show_alert=True)
                    return
                
                sessions = response.json()
        except Exception as e:
            logger.error(f"Failed to get chat history: {e}")
            await query.answer("❌ 获取失败", show_alert=True)
            return
        
        if not sessions or len(sessions) == 0:
            text = """
💬 **Chat 对话历史**

暂无对话记录

💡 提示：通过 Web 界面或 Chat 功能与 AI 对话后将显示历史记录
"""
        else:
            text = f"""
💬 **Chat 对话历史** (最近 {len(sessions)} 个会话)

"""
            for i, session in enumerate(sessions[:10], 1):
                session_id = session.get('id', '')[:8]
                title = session.get('title', '无标题')
                message_count = session.get('message_count', 0)
                
                text += f"""
{i}. **{self._escape_markdown(title)}**
   🆔 {session_id}... | 💬 {message_count} 条消息

"""
            
            text += """
💡 **提示:** 完整的对话管理请访问 Web 界面
"""
        
        keyboard = []
        self._add_back_button(keyboard, "menu_tasks")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_statistics(self, query):
        """Show usage statistics."""
        from web_app.services.scheduler_service import scheduler_service
        from web_app.services.device_service import device_service
        import httpx
        
        # Get task count
        tasks = scheduler_service.get_all_tasks_dict()
        total_tasks = len(tasks)
        
        # Get device count
        devices = device_service.get_all_devices()
        total_devices = len(devices)
        connected = sum(1 for d in devices if d.status == "connected")
        
        # Get chat sessions count
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:8080/api/chat/sessions",
                    timeout=5.0
                )
                if response.status_code == 200:
                    sessions = response.json()
                    total_chats = len(sessions)
                    total_messages = sum(s.get('message_count', 0) for s in sessions)
                else:
                    total_chats = 0
                    total_messages = 0
        except:
            total_chats = 0
            total_messages = 0
        
        # Get rules count
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:8080/api/rules/apps",
                    timeout=5.0
                )
                if response.status_code == 200:
                    data = response.json()
                    total_apps = len(data.get('apps', []))
                else:
                    total_apps = 0
        except:
            total_apps = 0
        
        text = f"""
📊 **使用统计**

📱 **设备统计**
• 设备总数: `{total_devices}`
• 在线设备: `{connected}` {'✅' if connected > 0 else '⏸️'}

📅 **任务统计**
• 定时任务: `{total_tasks}`

💬 **对话统计**
• 会话数: `{total_chats}`
• 消息数: `{total_messages}`

⚙️ **配置统计**
• 应用映射: `{total_apps}`

📈 **Bot 使用**
• 已实现功能: `17/17` ✅
• 功能完成度: `100%`

💡 **提示:** 更详细的统计信息请访问 Web 界面
"""
        
        keyboard = []
        self._add_back_button(keyboard, "menu_advanced")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_help_section(self, query, section: str):
        """Show help and documentation sections."""
        sections_map = {
            "help_guide": {
                "title": "📖 使用指南",
                "content": """
**AutoGLM Bot 功能导航**

🤖 **模型配置**
• 选择 AI 模型
• 调整模型参数
• 管理 API 密钥

📋 **任务管理**
• 执行自动化任务
• 管理定时任务
• 查看执行历史

📱 **设备管理**
• 选择操作设备
• 截图功能
• 管理设备 PIN

⚙️ **系统设置**
• 配置邮件通知
• 查看系统状态

📊 **高级功能**
• 系统诊断
• 规则配置
• 统计信息

💡 **快速开始:** 点击下方查看新手引导
""",
                "back_menu": "menu_help"
            },
            "help_quickstart": {
                "title": "🚀 快速开始",
                "content": """
**新手指南 - 3 步开始使用**

**1️⃣ 连接设备**
• 确保设备通过 ADB 连接
• 在 Web 界面或设备菜单查看设备状态

**2️⃣ 配置 AI 模型**
• 进入"模型配置"选择模型
• 配置 API 密钥（在 Web 界面）
• 调整模型参数

**3️⃣ 执行任务**
• 点击"执行任务"
• 选择设备
• 输入任务描述，AI 将自动执行

📸 **截图功能:**
• 选择设备后点击"截图"
• 支持自动解锁和锁定

⏰ **定时任务:**
• 在 Web 界面创建定时任务
• 在 Bot 中查看和管理

💡 需要更多帮助？访问 Web 界面获取详细文档
""",
                "back_menu": "menu_help"
            },
            "help_feedback": {
                "title": "💭 问题反馈",
                "content": """
**遇到问题？我们随时为您服务**

🐛 **报告 Bug**
• 访问 GitHub Issues
• 描述问题和复现步骤
• 附上日志信息

💡 **功能建议**
• 在 GitHub Discussions 分享想法
• 参与社区讨论

📧 **联系方式**
• GitHub: 查看项目仓库
• 社区: 加入讨论组

📊 **诊断信息**
• 使用"系统诊断"查看状态
• Web 界面提供详细日志

🙏 **感谢您的反馈，让 AutoGLM 越来越好！**
""",
                "back_menu": "menu_help"
            },
            "help_changelog": {
                "title": "📝 更新日志",
                "content": """
**最新版本更新**

**v2.0 - Telegram Bot 大升级** 🎉
• ✅ 完整的菜单系统（6大分类）
• ✅ 17个实用功能全部实现
• ✅ 模型配置和参数调整
• ✅ 定时任务管理
• ✅ 系统诊断和监控
• ✅ 规则配置查看
• ✅ 使用统计展示

**功能亮点:**
• 📱 多设备管理
• 🤖 多模型支持
• 📧 邮件通知
• 🔒 安全加密
• 🌐 Web + Bot 双界面

**已知问题:**
• 暂无

**即将到来:**
• 更多 AI 模型集成
• 增强的自动化功能
• 性能优化

💡 访问项目 GitHub 查看完整更新日志
""",
                "back_menu": "menu_help"
            }
        }
        
        section_data = sections_map.get(section, {})
        title = section_data.get("title", "帮助")
        content = section_data.get("content", "暂无内容")
        back_menu = section_data.get("back_menu", "menu_help")
        
        text = f"{title}\n{content}"
        
        keyboard = []
        self._add_back_button(keyboard, back_menu)
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_web_guidance(self, query, feature: str):
        """Show guidance for features that need Web interface."""
        guidance_map = {
            "devices_add": {
                "title": "➕ 添加设备",
                "icon": "📱",
                "content": """
**添加新设备需要在 Web 界面进行**

⚙️ **操作步骤:**
1. 打开 Web 界面 (http://localhost:8080)
2. 进入"设备管理"页面
3. 点击"配对设备"或"连接设备"
4. 按照提示完成配对

💡 **支持的连接方式:**
• USB 连接 (ADB)
• 无线连接 (ADB over WiFi)
• 网络配对

🔒 **安全提示:**
设备配对需要在设备上确认授权
""",
                "back_menu": "menu_devices"
            },
            "devices_files": {
                "title": "📁 文件管理",
                "icon": "📂",
                "content": """
**文件管理需要在 Web 界面进行**

⚙️ **功能说明:**
Web 界面提供完整的文件管理功能：
• 📂 浏览设备文件系统
• ⬆️ 上传文件到设备
• ⬇️ 下载设备文件
• 🗑️ 删除文件

💡 **访问方式:**
1. 打开 http://localhost:8080
2. 选择设备
3. 进入"文件管理"

🔒 **权限说明:**
需要设备授予存储权限
""",
                "back_menu": "menu_devices"
            },
            "settings_telegram": {
                "title": "🤖 Telegram 设置",
                "icon": "⚙️",
                "content": """
**Telegram Bot 配置**

当前 Bot 运行正常 ✅

⚙️ **配置项目:**
• Bot Token 配置
• 权限管理
• 群组设置

💡 **群组使用提示:**
在群组中使用需要关闭 Bot 的 Privacy Mode:
1. 找到 @BotFather
2. 发送 /mybots
3. 选择你的 Bot
4. Bot Settings → Group Privacy → Turn off

🔧 **高级配置:**
完整的 Bot 配置需要在配置文件或 Web 界面进行
""",
                "back_menu": "menu_settings"
            },
            "settings_logs": {
                "title": "📋 日志设置",
                "icon": "📝",
                "content": """
**系统日志配置**

⚙️ **日志功能:**
• 自动记录所有操作
• 错误日志追踪
• 性能监控

📁 **日志位置:**
`logs/autoglm_web_YYYYMMDD.log`

💡 **日志级别:**
当前: INFO
支持: DEBUG, INFO, WARNING, ERROR

🔧 **配置方式:**
日志配置需要修改系统配置文件

📊 **查看日志:**
• Web 界面提供日志查看器
• 使用系统诊断查看运行状态
""",
                "back_menu": "menu_settings"
            },
            "settings_ui": {
                "title": "🎨 UI 设置",
                "icon": "⚙️",
                "content": """
**界面设置**

⚙️ **可配置项:**
• Web 界面主题
• 语言设置
• 显示选项

💡 **默认设置:**
• 主题: 自动（跟随系统）
• 语言: 简体中文
• 显示: 全部功能

🔧 **修改方式:**
UI 配置需要在 Web 界面的设置页面进行

📱 **Telegram Bot:**
Bot 界面已针对移动端优化，无需额外配置
""",
                "back_menu": "menu_settings"
            }
        }
        
        guidance = guidance_map.get(feature, {})
        title = guidance.get("title", "功能说明")
        content = guidance.get("content", "该功能需要在 Web 界面进行配置")
        back_menu = guidance.get("back_menu", "main_menu")
        
        text = f"{title}\n{content}"
        
        keyboard = []
        self._add_back_button(keyboard, back_menu)
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    # === END REMAINING ===
    
    async def _handle_feature_stub(self, query, feature_name: str):
        """Handle placeholder for unimplemented features."""
        # Show visible message instead of popup
        text = f"""
🚧 **功能开发中**

**{feature_name}** 功能正在紧张开发中...

📅 敬请期待！我们会尽快上线此功能。

💡 提示：您可以继续使用其他已上线的功能。
"""
        keyboard = [[InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def send_photo(self, chat_id: int, photo_data: bytes, caption: str = ""):
        """Send a photo to a specific chat."""
        if not self._application or not self._running:
            logger.warning("Cannot send photo: bot not running")
            return

        try:
            await self._application.bot.send_photo(chat_id=chat_id, photo=photo_data, caption=caption)
        except Exception as e:
            logger.error(f"Failed to send photo: {e}")


# Global instance
telegram_bot_service = TelegramBotService()
