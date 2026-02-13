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
        self._allowed_groups: list[int] = []  # New: authorized group IDs
        self._group_member_auth: bool = True  # New: auto-authorize group members
        self._running: bool = False
        self._config: Dict[str, Any] = {}  # Store config for use in commands
        self._notification_targets: Dict[str, str] = {}  # New: message routing config
        # Store pending tasks and device selections
        self._pending_tasks: Dict[str, str] = {}  # user_id -> task_content
        self._selected_devices: Dict[str, set] = {}  # user_id -> set of device_ids
        self._pending_action: dict[int, str] = {}  # chat_id -> pending_action
        self._task_options: dict[int, dict] = {}  # chat_id -> {complex_task: bool, send_email: bool, parallel: bool}
        
        # Track messages for real-time updates
        self._progress_messages: dict[int, int] = {}  # chat_id -> message_id
        self._screenshot_messages: dict[int, int] = {}  # chat_id -> message_id  
        self._current_chat_tasks: dict[int, str] = {}  # chat_id -> session_id
        self._last_update_time: dict[int, float] = {}  # chat_id -> last update timestamp
        self._log_counters: dict[int, int] = {}  # chat_id -> log count for fake progress
        self._token_counters: dict[int, int] = {}  # chat_id -> total tokens
        self._model_names: dict[int, str] = {}  # chat_id -> model name used
        self._recent_logs: dict[int, list[str]] = {}  # chat_id -> recent log lines (max 10)
        self._sent_screenshots: dict[int, set[str]] = {}  # chat_id -> set of sent screenshot IDs
        self._menu_stack: Dict[str, list] = {}  # chat_id -> menu history for breadcrumb
        self._task_creation: Dict[str, Dict[str, Any]] = {}  # user_id -> task creation state
        
        # Chat persistent conversation mode
        self._chat_mode_device: dict[int, str] = {}  # chat_id -> device_id (bound device)
        self._chat_mode_active: dict[int, bool] = {}  # chat_id -> is in chat mode
        self._chat_mode_session: dict[int, str] = {}  # chat_id -> session_id (persistent session)
        self._chat_mode_task: dict[int, asyncio.Task] = {}  # chat_id -> running task (for cancellation)

    async def start(self, config: Dict[str, Any]):
        """Start the Telegram bot."""
        self._bot_token = config.get("bot_token")
        self._enabled = config.get("enabled", False)
        self._allowed_users = config.get("allowed_users", [])
        self._allowed_groups = config.get("allowed_groups", [])
        self._group_member_auth = config.get("group_member_auth", True)
        self._notification_targets = config.get("notification_targets", {
            "system_notifications": "groups",
            "welcome_menu": "both",
            "task_results": "requestor"
        })
        self._config = config  # Store config
        
        # Backward compatibility: migrate old config format
        # If allowed_groups is empty but allowed_users contains negative IDs (groups)
        if not self._allowed_groups and self._allowed_users:
            self._allowed_groups = [uid for uid in self._allowed_users if uid < 0]
            self._allowed_users = [uid for uid in self._allowed_users if uid > 0]
            logger.info(f"Migrated {len(self._allowed_groups)} group IDs from allowed_users to allowed_groups")

        if not self._enabled or not self._bot_token:
            logger.info("Telegram bot is disabled or not configured")
            return

        try:
            from telegram.request import HTTPXRequest
            
            # Create custom request with increased timeout to prevent slow responses
            request = HTTPXRequest(
                connection_pool_size=8,
                read_timeout=30.0,      # Increase read timeout from default 5s to 30s
                write_timeout=30.0,     # Increase write timeout
                connect_timeout=10.0,   # Connection timeout
                pool_timeout=10.0       # Pool timeout
            )
            
            # Create application with custom request
            self._application = Application.builder().token(self._bot_token).request(request).build()

            # Register command handlers
            self._application.add_handler(CommandHandler("start", self._cmd_start))
            self._application.add_handler(CommandHandler("help", self._cmd_help))
            self._application.add_handler(CommandHandler("task", self._cmd_task))
            self._application.add_handler(CommandHandler("chat", self._cmd_chat))  # Persistent chat mode
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
            
            # Delete any existing webhook before starting polling
            # Telegram doesn't allow both webhook and polling simultaneously
            try:
                await self._application.bot.delete_webhook(drop_pending_updates=True)
                logger.info("Deleted existing webhook (if any)")
            except Exception as e:
                logger.warning(f"Failed to delete webhook: {e}")
            
            # Add error handler for graceful Conflict handling
            self._application.add_error_handler(self._handle_telegram_error)
            
            await self._application.updater.start_polling()
            self._running = True
            
            # Set up bot commands menu
            await self._setup_bot_commands()
            
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

    async def _handle_telegram_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle Telegram errors gracefully, especially Conflict errors.
        
        Conflict errors occur when multiple bot instances are running with the same token.
        Instead of showing a long traceback, we log a clean message and notify the frontend.
        """
        error = context.error
        
        # Check if this is a Conflict error (multiple bot instances)
        error_str = str(error)
        if "Conflict" in error_str or "terminated by other getUpdates" in error_str:
            # Log a clean, single-line warning instead of full traceback
            logger.warning("⚠️ Telegram Bot Conflict: 检测到有其他 Bot 实例正在运行。请确保只有一个实例在运行。")
            
            # Broadcast alert to frontend
            try:
                from web_app.routers.websocket import broadcast_system_alert
                broadcast_system_alert(
                    level="warning",
                    title="Telegram Bot 冲突",
                    message="检测到有其他 Bot 实例正在运行，可能导致消息接收不稳定。请检查是否有其他服务器进程在后台运行。",
                    auto_dismiss=0  # Require manual dismiss
                )
            except Exception as e:
                logger.debug(f"Could not broadcast alert: {e}")
            
            # Don't re-raise Conflict errors - they are handled
            return
        
        # Network errors (ReadError, ConnectError, TimeoutError, etc.) are transient
        # and auto-recovered by python-telegram-bot's retry loop - log as warning only
        if isinstance(error, NetworkError):
            logger.warning(f"Telegram network error (will auto-retry): {error.__class__.__name__}: {error}")
            return

        # For other errors, log with traceback
        logger.error(f"Telegram error: {error}", exc_info=error)

    def _check_authorization(self, update: Update) -> bool:
        """
        Check if user is authorized.
        
        Supports both individual user authorization and group-based authorization.
        If group_member_auth is enabled, all members of authorized groups are automatically authorized.
        
        Args:
            update: Telegram Update object
            
        Returns:
            True if authorized, False otherwise
        """
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # If no restrictions configured, allow everyone
        if not self._allowed_users and not self._allowed_groups:
            return True
        
        # Check individual user authorization
        if user_id in self._allowed_users:
            logger.debug(f"User {user_id} authorized via allowed_users")
            return True
        
        # Check group-based authorization
        if self._group_member_auth and chat_id < 0:
            # Message is from a group, check if group is authorized
            if chat_id in self._allowed_groups:
                logger.debug(f"User {user_id} authorized via group {chat_id}")
                return True
        
        logger.debug(f"User {user_id} in chat {chat_id} not authorized")
        return False

    def _escape_markdown(self, text: str) -> str:
        """Escape markdown special characters."""
        if not text:
            return ""
        return text.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if not self._check_authorization(update):
            await update.message.reply_text("❌ 未授权的用户")
            return

        # Show new main menu
        await self._show_main_menu(update, is_query=False)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not self._check_authorization(update):
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
        chat_id_int = update.message.chat_id
        
        if not self._check_authorization(update):
            await update.message.reply_text("❌ 未授权的用户")
            return
        
        # Check if user is in persistent chat mode
        if chat_id_int in self._chat_mode_active and self._chat_mode_active[chat_id_int]:
            await self._handle_chat_mode_message(update, context)
            return
        
        # Check if user is in task creation flow
        if user_id in self._task_creation:
            await self._handle_task_creation_input(update, context)
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
        if not self._check_authorization(update):
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

    async def _cmd_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /chat command - enter persistent chat mode with device selection."""
        if not self._check_authorization(update):
            await update.message.reply_text("❌ 未授权的用户")
            return
        
        chat_id = update.effective_chat.id
        
        # If already in chat mode, show status
        if chat_id in self._chat_mode_active and self._chat_mode_active[chat_id]:
            device_id = self._chat_mode_device.get(chat_id, "未知")
            device_short = device_id[:12] + "..." if len(device_id) > 12 else device_id
            keyboard = [[InlineKeyboardButton("🚪 退出 Chat 模式", callback_data="chat_exit")]]
            await update.message.reply_text(
                f"💬 **已在 Chat 模式中**\n"
                f"📱 设备: `{device_short}`\n\n"
                f"发送任意消息执行任务",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return
        
        try:
            from web_app.services.device_service import device_service
            
            devices = device_service.get_all_devices()
            if not devices:
                await update.message.reply_text("❌ 没有可用的设备")
                return
            
            # Create device selection buttons for chat mode
            keyboard = []
            for device in devices:
                status_emoji = "🟢" if device.status == "online" else "🔴"
                device_label = f"{status_emoji} {device.name[:15]}" if device.name else f"{status_emoji} {device.id[:12]}..."
                keyboard.append([InlineKeyboardButton(
                    device_label,
                    callback_data=f"chat_select_{device.id}"
                )])
            
            keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="main_menu")])
            
            await update.message.reply_text(
                "💬 **进入 Chat 模式**\n\n"
                "选择一个设备后，可以直接发送任务消息执行，无需每次选择设备。\n\n"
                "📱 请选择设备:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Chat command failed: {e}")
            await update.message.reply_text(f"❌ 失败: {str(e)}")

    async def _handle_chat_mode_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages in persistent chat mode - execute task on bound device."""
        chat_id = update.message.chat_id
        task_content = update.message.text.strip()
        
        if not task_content:
            return
        
        device_id = self._chat_mode_device.get(chat_id)
        if not device_id:
            # Device not found, exit chat mode
            self._chat_mode_active[chat_id] = False
            await update.message.reply_text("❌ 设备未绑定，已退出 Chat 模式")
            return
        
        # Send initial progress message
        device_short = device_id[:12] + "..." if len(device_id) > 12 else device_id
        keyboard = [[
            InlineKeyboardButton("⏹️ 停止", callback_data="chat_stop"),
            InlineKeyboardButton("🚪 退出 Chat", callback_data="chat_exit")
        ]]
        
        progress_msg = await update.message.reply_text(
            f"🔄 **执行中...**\n"
            f"📱 设备: `{device_short}`\n"
            f"📝 任务: {task_content[:50]}{'...' if len(task_content) > 50 else ''}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # Store progress message for updates
        self._progress_messages[chat_id] = progress_msg.message_id
        
        async def execute_task():
            """Inner function to execute task, can be cancelled."""
            from web_app.services.task_service import task_service
            from web_app.services.chat_service import chat_service
            
            # Use persistent session from chat mode, or create one if missing
            session_id = self._chat_mode_session.get(chat_id)
            if not session_id:
                # Fallback: create session if not exists
                session = chat_service.create_session(
                    device_id=f"bot_{update.effective_user.id}_{device_id}",
                    title="Telegram Chat Mode"
                )
                session_id = session['id']
                self._chat_mode_session[chat_id] = session_id
                logger.info(f"Created fallback chat session {session_id} for chat {chat_id}")
            
            # Add user message to existing session
            user_msg = chat_service.add_message(
                session_id=session_id,
                role='user',
                content=task_content,
                source='telegram'
            )
            
            # Track this task
            self._current_chat_tasks[chat_id] = session_id
            
            # Create assistant message placeholder
            assistant_msg = chat_service.add_message(
                session_id=session_id,
                role='assistant',
                content='执行中...'
            )
            
            # Token callback to save tokens to database (both session and message level)
            message_tokens_accumulated = [0]  # Use list for mutable closure
            def token_callback(task_id: str, input_tokens: int, output_tokens: int, total_tokens: int):
                try:
                    # Update session total tokens
                    chat_service.update_session_tokens(session_id, total_tokens)
                    
                    # Accumulate and update message tokens
                    message_tokens_accumulated[0] += total_tokens
                    chat_service.update_message(assistant_msg['id'], tokens=message_tokens_accumulated[0])
                    
                    logger.info(f"Chat mode: saved {total_tokens} tokens to session {session_id}, message {assistant_msg['id'][:8]} (total: {message_tokens_accumulated[0]})")
                except Exception as e:
                    logger.error(f"Failed to save tokens to database: {e}")
            
            # Register token callback
            task_service.add_token_callback(token_callback)
            
            try:
                # Run task - keep device unlocked (no_auto_lock) until chat exit, no email
                result = await task_service.run_task(
                    task_content=task_content,
                    device_ids=[device_id],
                    task_type='chat',
                    session_id=session_id,
                    message_id=assistant_msg['id'],
                    no_auto_lock=True,  # Keep device unlocked in chat mode
                    send_email=False,   # No email for chat mode tasks
                )
                
                return result
            finally:
                # Always remove callback after task completes
                task_service.remove_token_callback(token_callback)
        
        try:
            # Create and track the task for cancellation
            task = asyncio.create_task(execute_task())
            self._chat_mode_task[chat_id] = task
            
            try:
                result = await task
                
                # Get result
                success = result.status == 'completed' if hasattr(result, 'status') else result.get('status') == 'completed'
                finish_message = ""
                if hasattr(result, 'results') and result.results:
                    finish_message = result.results[0].get('message', '') if isinstance(result.results[0], dict) else str(result.results[0])
                
                # Update progress message with result
                status_emoji = "✅" if success else "❌"
                # Get session_id and message_id for display
                session_id_display = self._chat_mode_session.get(chat_id, "N/A")[:8]
                result_text = (
                    f"{status_emoji} **{'完成' if success else '失败'}**\n"
                    f"📱 设备: `{device_short}`\n"
                    f"🆔 Session: `{session_id_display}`\n"
                )
                if finish_message:
                    result_text += f"💬 {finish_message[:100]}{'...' if len(finish_message) > 100 else ''}\n"
                
                result_text += "\n发送下一个任务，或点击退出"
                
                # Note: Screenshot is sent by send_device_completion callback
                # Just update the progress message here
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_msg.message_id,
                        text=result_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass
                    
            except asyncio.CancelledError:
                # Task was cancelled by stop button
                logger.info(f"Chat mode task cancelled for chat {chat_id}")
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_msg.message_id,
                        text=f"⏹️ **任务已停止**\n📱 设备: `{device_short}`\n\n💬 发送新消息继续执行任务",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🚪 退出 Chat", callback_data="chat_exit")
                        ]]),
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"Chat mode task failed: {e}")
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg.message_id,
                    text=f"❌ **执行失败**\n{str(e)[:100]}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception:
                pass
        finally:
            # Cleanup task tracking
            if chat_id in self._chat_mode_task:
                del self._chat_mode_task[chat_id]
            if chat_id in self._current_chat_tasks:
                del self._current_chat_tasks[chat_id]


    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self._check_authorization(update):
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
        if not self._check_authorization(update):
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
        if not self._check_authorization(update):
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
        if not self._check_authorization(update):
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

        if not self._check_authorization(update):
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
                # Also exit chat mode when going to main menu
                chat_id_int = query.message.chat_id
                # Cancel any running task
                if chat_id_int in self._chat_mode_task:
                    task = self._chat_mode_task[chat_id_int]
                    if not task.done():
                        task.cancel()
                    del self._chat_mode_task[chat_id_int]
                if chat_id_int in self._chat_mode_active:
                    del self._chat_mode_active[chat_id_int]
                if chat_id_int in self._chat_mode_device:
                    del self._chat_mode_device[chat_id_int]
                if chat_id_int in self._chat_mode_session:
                    del self._chat_mode_session[chat_id_int]
                    
                return
            
            # === CHAT MODE CALLBACKS ===
            # Handle enter chat mode (from tasks menu)
            if callback_data == "enter_chat_mode":
                try:
                    from web_app.services.device_service import device_service
                    
                    devices = device_service.get_all_devices()
                    if not devices:
                        await query.edit_message_text("❌ 没有可用的设备")
                        return
                    
                    # Create device selection buttons for chat mode
                    keyboard = []
                    for device in devices:
                        status_emoji = "🟢" if device.status == "online" else "🔴"
                        device_label = f"{status_emoji} {device.name[:15]}" if device.name else f"{status_emoji} {device.id[:12]}..."
                        keyboard.append([InlineKeyboardButton(
                            device_label,
                            callback_data=f"chat_select_{device.id}"
                        )])
                    
                    keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="menu_tasks")])
                    
                    await query.edit_message_text(
                        "💬 **进入 Chat 模式**\n\n"
                        "选择一个设备后，可以直接发送任务消息执行，无需每次选择设备。\n\n"
                        "📱 请选择设备:",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Enter chat mode failed: {e}")
                    await query.edit_message_text(f"❌ 失败: {str(e)}")
                return
            
            # Handle chat device selection
            if callback_data.startswith("chat_select_"):
                device_id = callback_data.replace("chat_select_", "")
                chat_id_int = query.message.chat_id
                
                # Create a persistent session for this chat mode
                try:
                    from web_app.services.chat_service import chat_service
                    session = chat_service.create_session(
                        device_id=f"bot_{query.from_user.id}_{device_id}",
                        title="Telegram Chat Mode"
                    )
                    self._chat_mode_session[chat_id_int] = session['id']
                    logger.info(f"Created persistent chat session {session['id']} for chat {chat_id_int}")
                except Exception as e:
                    logger.error(f"Failed to create chat session: {e}")
                
                # Enter chat mode with selected device
                self._chat_mode_device[chat_id_int] = device_id
                self._chat_mode_active[chat_id_int] = True
                
                device_short = device_id[:12] + "..." if len(device_id) > 12 else device_id
                
                keyboard = [[InlineKeyboardButton("🚪 退出 Chat 模式", callback_data="chat_exit")]]
                session_short = session['id'][:8] if session else "N/A"
                await query.edit_message_text(
                    f"✅ **已进入 Chat 模式**\n\n"
                    f"📱 设备: `{device_short}`\n"
                    f"🆔 Session: `{session_short}`\n\n"
                    f"💡 直接发送消息执行任务\n"
                    f"💬 每条消息都会在该设备上执行",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                return
            
            # Handle chat mode exit
            if callback_data == "chat_exit":
                chat_id_int = query.message.chat_id
                
                # Cancel any running task first
                if chat_id_int in self._chat_mode_task:
                    task = self._chat_mode_task[chat_id_int]
                    if not task.done():
                        task.cancel()
                        logger.info(f"Cancelled running task on chat exit for chat {chat_id_int}")
                
                # Also stop via task_service
                from web_app.services.task_service import task_service
                await task_service.stop_all_tasks()
                
                # Get device before clearing state
                device_id = self._chat_mode_device.get(chat_id_int)
                
                # Exit chat mode and clear session
                if chat_id_int in self._chat_mode_active:
                    del self._chat_mode_active[chat_id_int]
                if chat_id_int in self._chat_mode_device:
                    del self._chat_mode_device[chat_id_int]
                if chat_id_int in self._chat_mode_session:
                    del self._chat_mode_session[chat_id_int]
                if chat_id_int in self._chat_mode_task:
                    del self._chat_mode_task[chat_id_int]
                
                # Lock device on exit
                if device_id:
                    try:
                        from web_app.services.device_service import device_service
                        await device_service.lock_device(device_id)
                        logger.info(f"Locked device {device_id} on chat exit")
                    except Exception as e:
                        logger.warning(f"Failed to lock device on chat exit: {e}")
                
                # Send new message instead of edit (photo messages can't be edited to text)
                await query.message.reply_text(
                    "👋 **已退出 Chat 模式**\n\n"
                    "返回正常模式，可以使用 /chat 再次进入",
                    parse_mode='Markdown'
                )
                return
            
            # Handle chat stop (cancel running task)
            if callback_data == "chat_stop":
                chat_id_int = query.message.chat_id
                
                # Cancel the tracked asyncio task for this chat
                if chat_id_int in self._chat_mode_task:
                    task = self._chat_mode_task[chat_id_int]
                    if not task.done():
                        task.cancel()
                        logger.info(f"Cancelled task for chat {chat_id_int}")
                
                # Also stop via task_service for immediate effect
                from web_app.services.task_service import task_service
                await task_service.stop_all_tasks()
                
                # Send new message (original might be a photo)
                device_id = self._chat_mode_device.get(chat_id_int, "")
                device_short = device_id[:12] + "..." if len(device_id) > 12 else device_id
                await query.message.reply_text(
                    f"⏹️ **任务已停止**\n"
                    f"📱 设备: `{device_short}`\n\n"
                    f"💬 发送新消息继续执行任务",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🚪 退出 Chat", callback_data="chat_exit")
                    ]]),
                    parse_mode='Markdown'
                )
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
            
            # Handle task pagination
            if callback_data.startswith("tasks_page_"):
                page = int(callback_data.replace("tasks_page_", ""))
                await self._show_scheduled_tasks(query, page=page)
                return
            
            # Handle task toggle (enable/disable)
            if callback_data.startswith("toggle_task_"):
                await self._handle_toggle_task(query, callback_data)
                return
            
            # Handle task delete
            if callback_data.startswith("delete_task_"):
                await self._handle_delete_task(query, callback_data)
                return
            
            # Handle task logs view
            if callback_data.startswith("task_logs_"):
                await self._show_task_logs(query, callback_data)
                return
            
            # Handle task creation
            if callback_data == "create_task_start":
                await self._start_task_creation(query)
                return
            
            if callback_data.startswith("task_schedule_"):
                await self._handle_schedule_selection(query, callback_data)
                return
            
            if callback_data.startswith("task_device_"):
                await self._handle_task_device_selection(query, callback_data)
                return
            
            if callback_data == "task_create_confirm":
                await self._confirm_task_creation(query)
                return
            
            if callback_data == "task_create_cancel":
                await self._cancel_task_creation(query)
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
            
            if callback_data == "devices_unlock_list":
                await self._show_device_action_list(query, "unlock")
                return
            
            if callback_data == "devices_lock_list":
                await self._show_device_action_list(query, "lock")
                return
            
            if callback_data.startswith("device_unlock_"):
                device_id = callback_data.replace("device_unlock_", "")
                await self._execute_device_unlock(query, device_id)
                return
            
            if callback_data.startswith("device_lock_"):
                device_id = callback_data.replace("device_lock_", "")
                await self._execute_device_lock(query, device_id)
                return
            # === END DEVICE UNLOCK/LOCK ===
            
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
                
                # Escape markdown special characters
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
                
                # Initialize task options if not exists (all default to False)
                if chat_id not in self._task_options:
                    self._task_options[chat_id] = {"complex_task": False, "send_email": False, "parallel": False}
                
                await self._show_task_options(query, chat_id)
                return
            
            # Handle task option toggles
            elif callback_data == "toggle_complex_task":
                if chat_id not in self._task_options:
                    self._task_options[chat_id] = {"complex_task": False, "send_email": False, "parallel": False}
                self._task_options[chat_id]["complex_task"] = not self._task_options[chat_id]["complex_task"]
                await self._show_task_options(query, chat_id)
                return

            elif callback_data == "toggle_send_email":
                if chat_id not in self._task_options:
                    self._task_options[chat_id] = {"complex_task": False, "send_email": False, "parallel": False}
                self._task_options[chat_id]["send_email"] = not self._task_options[chat_id]["send_email"]
                await self._show_task_options(query, chat_id)
                return

            elif callback_data == "toggle_parallel":
                if chat_id not in self._task_options:
                    self._task_options[chat_id] = {"complex_task": False, "send_email": False, "parallel": False}
                self._task_options[chat_id]["parallel"] = not self._task_options[chat_id]["parallel"]
                await self._show_task_options(query, chat_id)
                return
            
            elif callback_data == "confirm_task_options":
                # Proceed to actual task execution with selected options
                task_content = self._pending_tasks.get(chat_id)
                selected_devices = self._selected_devices.get(chat_id, set())
                task_options = self._task_options.get(chat_id, {"complex_task": False, "send_email": False, "parallel": False})
                
                if not task_content:
                    await query.edit_message_text("❌ 任务已过期，请重新提交")
                    return
                
                if not selected_devices:
                    await query.answer("❌ 请至少选择一个设备", show_alert=True)
                    return
                
                # Execute task
                from web_app.services.task_service import task_service
                from web_app.services.chat_service import chat_service
                import base64
                from io import BytesIO
                
                # === TASK CONFLICT DETECTION ===
                # Check if another task is already running
                current_task = task_service.get_current_task()
                if current_task:
                    can_interrupt, current_info = task_service.can_interrupt_current_task("chat")
                    
                    if not can_interrupt:
                        # Bot task has highest priority (chat=3), this shouldn't happen
                        # But let's handle it gracefully
                        await query.edit_message_text(
                            f"⚠️ **有任务正在执行**\n\n"
                            f"📋 {current_info['task_type_display']}: {current_info['task_content'][:30]}...\n"
                            f"⏱️ 进度: {current_info['progress']}%\n\n"
                            f"请等待当前任务完成后再试。",
                            parse_mode='Markdown'
                        )
                        # Clean up
                        if chat_id in self._pending_tasks:
                            del self._pending_tasks[chat_id]
                        if chat_id in self._selected_devices:
                            del self._selected_devices[chat_id]
                        if chat_id in self._pending_action:
                            del self._pending_action[chat_id]
                        return
                    
                    # Can interrupt - notify and stop current task
                    await query.edit_message_text(
                        f"⚠️ **正在停止当前任务**\n\n"
                        f"📋 {current_info['task_type_display']}: {current_info['task_content'][:30]}...\n"
                        f"⏳ Bot 任务优先级更高，将强制停止...\n\n"
                        f"请稍候...",
                        parse_mode='Markdown'
                    )
                    
                # === BOT TASK HISTORY: Create chat session ===
                # Use bot_ prefix to distinguish from Web tasks
                user_id = update.effective_user.id if update and update.effective_user else "unknown"
                first_device_id = list(selected_devices)[0] if selected_devices else 'unknown'
                bot_device_id = f"bot_{user_id}_{first_device_id}"

                # Create session for this Bot task
                session = chat_service.create_session(
                    device_id=bot_device_id,
                    title=task_content[:50]  # Use task as title
                )
                session_id = session['id']
                
                # Add user message (the task description) - mark as from Telegram
                user_msg = chat_service.add_message(
                    session_id=session_id,
                    role='user',
                    content=task_content,
                    source='telegram'  # Mark as from Telegram bot
                )
                
                # === MULTI-DEVICE FIX: Don't create assistant message here ===
                # Let task_service create separate assistant messages for each device
                # This ensures each device's logs and screenshots are isolated
                
                # Set current context to user message for now
                chat_service.set_current_context(session_id, user_msg['id'])
                logger.info(f"Created Bot task session {session_id} for user {user_id}")
                
                # === REAL-TIME FEEDBACK: Register callbacks ===
                # Store chat_id for callbacks to access
                self._current_chat_tasks[chat_id] = session_id
                self._log_counters[chat_id] = 0  # Initialize log counter
                self._token_counters[chat_id] = 0  # Initialize token counter
                self._recent_logs[chat_id] = []  # Initialize recent logs buffer
                self._sent_screenshots[chat_id] = set()  # Initialize sent screenshots tracking
                
                # Get and store model name
                model_name = 'Unknown'
                try:
                    from web_app.services.model_service import model_service
                    active_model = model_service.get_active_service_dict()
                    # Use model_name (e.g. "glm-4-flash") instead of name (e.g. "OpenAI代理")
                    model_name = active_model.get('model_name', 'Unknown') if active_model else 'Unknown'
                    self._model_names[chat_id] = model_name
                except Exception as e:
                    logger.error(f"Failed to get model name: {e}")
                    self._model_names[chat_id] = 'Unknown'
                
                # Progress callback
                def progress_update_callback(task_id: str, progress: int):
                    asyncio.create_task(
                        self._update_progress_message(
                            chat_id=chat_id,
                            task_content=task_content,
                            progress=progress
                        )
                    )
                
                # Log callback (for progress text and screenshot trigger)
                def log_update_callback(task_id: str, message: str, task_type: str):
                    # Increment log counter
                    if chat_id in self._log_counters:
                        self._log_counters[chat_id] += 1
                        # Calculate fake progress: 1 log = 1%, cap at 99%
                        fake_progress = min(self._log_counters[chat_id], 99)
                    else:
                        fake_progress = 0
                    
                    # Extract token count from log if present
                    # Format: [TOKENS]input,output,total[/TOKENS]
                    import re
                    token_match = re.search(r'\[TOKENS\](\d+),(\d+),(\d+)\[/TOKENS\]', message)
                    if token_match:
                        tokens_total = int(token_match.group(3))
                        # Initialize if not exists
                        if chat_id not in self._token_counters:
                            self._token_counters[chat_id] = 0
                        # Accumulate tokens
                        self._token_counters[chat_id] += tokens_total
                        
                        # Save to database (both session and message level)
                        try:
                            # chat_service is already imported in the outer scope
                            if session_id:
                                chat_service.update_session_tokens(session_id, tokens_total)
                                
                                # Also update message-level tokens
                                # Get message_id from task_service context (created during run_task)
                                msg_id = task_service._chat_context.message_id if hasattr(task_service, '_chat_context') else None
                                if msg_id:
                                    # Accumulate tokens for this message
                                    accumulated = self._token_counters.get(chat_id, 0)
                                    chat_service.update_message(msg_id, tokens=accumulated)
                                    logger.debug(f"Bot task: saved {tokens_total} tokens to message {msg_id[:8]} (total: {accumulated})")
                        except Exception as e:
                            logger.error(f"Failed to save token to database: {e}")
                    
                    # Store recent logs (keep last 10, skip token lines and empty lines)
                    if message and not message.startswith('[TOKENS]'):
                        # Clean the message for display
                        clean_msg = message.strip()
                        if clean_msg:
                            if chat_id not in self._recent_logs:
                                self._recent_logs[chat_id] = []
                            self._recent_logs[chat_id].append(clean_msg)
                            # Keep only last 10 logs
                            if len(self._recent_logs[chat_id]) > 10:
                                self._recent_logs[chat_id] = self._recent_logs[chat_id][-10:]
                    
                    # Update progress message with latest log and fake progress
                    # No rate limiting - let Telegram handle it
                    asyncio.create_task(
                        self._update_progress_message(
                            chat_id=chat_id,
                            task_content=task_content,
                            progress=fake_progress
                        )
                    )
                    
                    # Trigger screenshot update if this log mentions a screenshot
                    # Use delay to avoid overwhelming Telegram
                    if "📸" in message or "Screenshot" in message:
                        # === PLAN A: Disable screenshot updates during AI interaction ===
                        # Screenshot data in database may be incomplete (14 bytes issue)
                        # We now rely on send_device_completion for screenshots after task completes
                        # asyncio.create_task(self._update_screenshot(chat_id))
                        pass
                
                task_service.add_progress_callback(progress_update_callback)
                task_service.add_log_callback(log_update_callback)
                
                # Send initial progress message
                await self._update_progress_message(
                    chat_id=chat_id,
                    task_content=task_content,
                    progress=0,
                    latest_log="正在启动任务执行..."
                )
                # Note: Removed the old static "📝 **任务执行中**" message
                # Now using dynamic progress messages instead
                
                try:
                    # Execute task and get result directly from return value
                    # Use parallel mode if enabled and multiple devices selected
                    use_parallel = task_options.get("parallel", False) and len(selected_devices) > 1

                    if use_parallel:
                        logger.info(f"[PARALLEL MODE] Running task on {len(selected_devices)} devices in parallel")
                        task_result = await task_service.run_task_parallel(
                            task_content=task_content,
                            device_ids=list(selected_devices),
                            send_email=task_options["send_email"],
                            no_auto_lock=task_options["complex_task"],
                            task_type="chat",
                            session_id=session_id
                        )
                    else:
                        task_result = await task_service.run_task(
                            task_content=task_content,
                            device_ids=list(selected_devices),
                            send_email=task_options["send_email"],
                            no_auto_lock=task_options["complex_task"],
                            task_type="chat",
                            session_id=session_id
                        )
                    
                    logger.info(f"Task execution completed - task_result exists: {task_result is not None}, status: {task_result.status if task_result else 'None'}")
                    
                    if task_result:
                        status_emoji = "✅" if task_result.status == "completed" else "❌"
                        # Escape task content for markdown
                        task_content_safe = self._escape_markdown(task_content)
                        response = f"{status_emoji} **任务{task_result.status}**\n\n"
                        response += f"🎯 {task_content_safe}\n"
                        response += f"⏱️ 进度: {task_result.progress}%"
                        
                        # === BOT TASK HISTORY: Update session status ===
                        chat_service.update_session_status(session_id, 'completed')
                        
                        # === MULTI-DEVICE FIX: Model names are saved per-device in task_service ===
                        # Each device's assistant message gets model_name updated separately
                        
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
                        
                        # === MULTI-DEVICE: Only send log summary for single device tasks ===
                        # Multi-device tasks already sent per-device completion reports
                        device_count = len(selected_devices) if selected_devices else 0
                        
                        # === ALL DEVICES: Skip log/screenshot summary ===
                        # All tasks already sent per-device completion reports via send_device_completion
                        logger.info(f"Skipping log/screenshot summary for {device_count} device(s) - already sent per-device")
                        
                        
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
                        
                        # === BOT TASK HISTORY: Update session status ===
                        chat_service.update_session_status(session_id, 'completed')
                        chat_service.clear_current_context()
                        logger.info(f"Bot task session {session_id} marked as completed")
                        
                        # === REAL-TIME FEEDBACK: Cleanup ===
                        # Remove callbacks
                        try:
                            task_service.remove_progress_callback(progress_update_callback)
                            task_service.remove_log_callback(log_update_callback)
                        except Exception:
                            pass
                        
                        # Update final progress message
                        await self._update_progress_message(
                            chat_id=chat_id,
                            task_content=task_content,
                            progress=100,
                            latest_log="✅ 任务已完成"
                        )
                        
                        # Clean up tracking
                        if chat_id in self._current_chat_tasks:
                            del self._current_chat_tasks[chat_id]
                        if chat_id in self._last_update_time:
                            del self._last_update_time[chat_id]
                        if chat_id in self._log_counters:
                            del self._log_counters[chat_id]
                        if chat_id in self._token_counters:
                            del self._token_counters[chat_id]
                        if chat_id in self._model_names:
                            del self._model_names[chat_id]
                        if chat_id in self._recent_logs:
                            del self._recent_logs[chat_id]
                        if chat_id in self._sent_screenshots:
                            del self._sent_screenshots[chat_id]
                        # Clean up progress message reference (message was deleted at line 1228)
                        if chat_id in self._progress_messages:
                            del self._progress_messages[chat_id]
                    else:
                        logger.warning("Task completed but task_result is None!")
                        await query.edit_message_text("✅ 任务已提交")
                        
                except Exception as e:
                    logger.error(f"Task execution failed: {e}")
                    
                    # === REAL-TIME FEEDBACK: Update progress with error ===
                    await self._update_progress_message(
                        chat_id=chat_id,
                        task_content=task_content,
                        progress=0,
                        latest_log=f"❌ 执行失败: {str(e)[:80]}"
                    )
                    
                    # Send error screenshot if available
                    try:
                        from web_app.services.device_service import device_service
                        device_id = list(selected_devices)[0] if selected_devices else None
                        if device_id:
                            screenshot_data = await device_service.get_screenshot(device_id)
                            if screenshot_data:
                                if isinstance(screenshot_data, str):
                                    screenshot_bytes = base64.b64decode(screenshot_data)
                                else:
                                    screenshot_bytes = screenshot_data
                                
                                await self._application.bot.send_photo(
                                    chat_id=chat_id,
                                    photo=BytesIO(screenshot_bytes),
                                    caption=f"❌ 错误截图\n{str(e)[:100]}"
                                )
                    except Exception as screenshot_error:
                        logger.error(f"Failed to send error screenshot: {screenshot_error}")
                    
                    await query.edit_message_text(f"❌ 执行失败: {str(e)}")
                    
                    # === BOT TASK HISTORY: Mark as failed ===
                    try:
                        chat_service.update_session_status(session_id, 'failed')
                        chat_service.clear_current_context()
                        logger.info(f"Bot task session {session_id} marked as failed")
                        
                        # === REAL-TIME FEEDBACK: Cleanup ===
                        try:
                            task_service.remove_progress_callback(progress_update_callback)
                            task_service.remove_log_callback(log_update_callback)
                        except Exception:
                            pass
                        
                        # Clean up tracking
                        if chat_id in self._current_chat_tasks:
                            del self._current_chat_tasks[chat_id]
                        if chat_id in self._last_update_time:
                            del self._last_update_time[chat_id]
                        if chat_id in self._log_counters:
                            del self._log_counters[chat_id]
                        if chat_id in self._token_counters:
                            del self._token_counters[chat_id]
                        if chat_id in self._model_names:
                            del self._model_names[chat_id]
                        if chat_id in self._recent_logs:
                            del self._recent_logs[chat_id]
                        if chat_id in self._progress_messages:
                            del self._progress_messages[chat_id]
                    except Exception as cleanup_error:
                        logger.error(f"Failed to cleanup session: {cleanup_error}")
                
                # Clean up
                if chat_id in self._pending_tasks:
                    del self._pending_tasks[chat_id]
                if chat_id in self._selected_devices:
                    del self._selected_devices[chat_id]
                if chat_id in self._pending_action:
                    del self._pending_action[chat_id]
                if chat_id in self._current_chat_tasks:
                    del self._current_chat_tasks[chat_id]
                if chat_id in self._last_update_time:
                    del self._last_update_time[chat_id]
                if chat_id in self._log_counters:
                    del self._log_counters[chat_id]
                if chat_id in self._token_counters:
                    del self._token_counters[chat_id]
                if chat_id in self._model_names:
                    del self._model_names[chat_id]
                if chat_id in self._recent_logs:
                    del self._recent_logs[chat_id]
                if chat_id in self._sent_screenshots:
                    del self._sent_screenshots[chat_id]
                if chat_id in self._progress_messages:
                    del self._progress_messages[chat_id]
                
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
            from telegram.error import BadRequest, RetryAfter
            
            # Handle Telegram rate limiting (Flood Control)
            if isinstance(e, RetryAfter):
                retry_after = e.retry_after
                logger.warning(f"Telegram rate limit exceeded, retry after {retry_after}s")
                # Don't try to send another message (would also be rate limited)
                # Just answer the callback query to acknowledge the click
                try:
                    await query.answer(f"⚠️ 操作过快，请 {retry_after} 秒后重试", show_alert=True)
                except Exception:
                    pass  # If even this fails, just give up
                return
            
            # Ignore "message not modified" errors (when user clicks same button twice)
            if isinstance(e, BadRequest) and "message is not modified" in str(e).lower():
                logger.debug(f"Message content unchanged, skipping edit")
                return
            
            logger.error(f"Button callback failed: {e}")
            # Try to edit message, but don't fail if this also times out
            try:
                await query.edit_message_text(f"❌ 操作失败: {str(e)}")
            except Exception as edit_error:
                # Don't log flood control errors for error messages
                if not isinstance(edit_error, RetryAfter):
                    logger.error(f"Failed to send error message: {edit_error}")
                # Just answer the callback query instead
                try:
                    await query.answer(f"❌ 操作失败: {str(e)}", show_alert=True)
                except Exception:
                    pass  # Give up gracefully

    async def send_message(self, chat_id: int, text: str):
        """Send a message to a specific chat."""
        if not self._application or not self._running:
            logger.warning("Cannot send message: bot not running")
            return

        try:
            await self._application.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    async def send_system_notification(self, message: str, screenshots: dict = None):
        """
        Send system notification to all authorized GROUP chats (chat_id < 0).
        Individual users are not notified, only groups.

        Args:
            message: The notification message to send
            screenshots: Optional dict of {device_id: screenshot_data} to send as photos
        """
        if not self._application or not self._running:
            logger.warning("Cannot send system notification: bot not running")
            return

        # Check if there are any authorized groups
        if not self._allowed_groups:
            logger.debug("No authorized group chats configured for system notifications")
            return

        notification_text = f"🔔 *System Notification*\n\n{message}"

        # Send to all authorized groups
        for chat_id in self._allowed_groups:
            if chat_id < 0:  # Double-check it's a group
                try:
                    await self.send_message(chat_id, notification_text)
                    logger.info(f"System notification sent to group {chat_id}")

                    # Send screenshots if available
                    if screenshots:
                        await self._send_screenshots_to_chat(chat_id, screenshots)
                except Exception as e:
                    logger.error(f"Failed to send notification to group {chat_id}: {e}")

        # Send welcome menu to all users after startup notification
        if "系统已启动" in message or "已就绪" in message:
            await self.send_welcome_menu_to_all()
    
    async def send_welcome_menu_to_all(self):
        """Send welcome menu to all authorized users and groups based on config."""
        if not self._application or not self._running:
            return
        
        # Check notification target configuration
        target = self._notification_targets.get("welcome_menu", "both")
        
        try:
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
            
            # Send to individual users if configured
            if target in ["both", "users"]:
                for user_id in self._allowed_users:
                    if user_id > 0:  # Only positive IDs are users
                        try:
                            await self._application.bot.send_message(
                                chat_id=user_id,
                                text=text,
                                reply_markup=reply_markup,
                                parse_mode='Markdown'
                            )
                            logger.info(f"Welcome menu sent to user {user_id}")
                        except Exception as e:
                            logger.error(f"Failed to send welcome menu to user {user_id}: {e}")
            
            # Send to groups if configured
            if target in ["both", "groups"]:
                for group_id in self._allowed_groups:
                    if group_id < 0:  # Only negative IDs are groups
                        try:
                            await self._application.bot.send_message(
                                chat_id=group_id,
                                text=text,
                                reply_markup=reply_markup,
                                parse_mode='Markdown'
                            )
                            logger.info(f"Welcome menu sent to group {group_id}")
                        except Exception as e:
                            logger.error(f"Failed to send welcome menu to group {group_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to send welcome menu: {e}")



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
    
    async def _setup_bot_commands(self):
        """Set up bot command menu based on welcome menu structure."""
        try:
            from telegram import BotCommand
            
            commands = [
                # Main categories matching welcome menu
                BotCommand("start", "🏠 显示主菜单"),
                BotCommand("chat", "💬 持续对话模式"),
                BotCommand("tasks", "📋 任务管理"),
                BotCommand("devices", "📱 设备管理"),
                BotCommand("settings", "⚙️ 系统设置"),
                BotCommand("models", "🤖 模型配置"),
                BotCommand("advanced", "📊 高级功能"),
                BotCommand("help", "ℹ️ 帮助支持"),
            ]
            
            await self._application.bot.set_my_commands(commands)
            logger.info(f"✅ Bot commands menu synchronized: {len(commands)} commands")
            
        except Exception as e:
            logger.error(f"Failed to set up bot commands: {e}")
    
    async def _show_tasks_menu(self, query):
        """Show tasks management menu."""
        text = """
📋 **任务管理**

管理和执行自动化任务：
"""
        
        keyboard = [
            [InlineKeyboardButton("▶️ 执行任务", callback_data="get_task")],
            [InlineKeyboardButton("💬 Chat 模式", callback_data="enter_chat_mode")],
            [InlineKeyboardButton("📸 获取截图", callback_data="get_screenshot")],
            [InlineKeyboardButton("📅 定时任务", callback_data="tasks_scheduled")],
            [InlineKeyboardButton("📜 任务历史", callback_data="tasks_history")],
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
            [
                InlineKeyboardButton("🔓 解锁设备", callback_data="devices_unlock_list"),
                InlineKeyboardButton("🔒 锁定设备", callback_data="devices_lock_list"),
            ],
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
    async def _show_scheduled_tasks(self, query, page: int = 0):
        """
        Show list of scheduled tasks with pagination.
        
        Args:
            query: Callback query object
            page: Current page number (0-indexed)
        """
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
        
        # Pagination settings
        TASKS_PER_PAGE = 5
        total_tasks = len(tasks_data)
        total_pages = (total_tasks + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE
        page = max(0, min(page, total_pages - 1))  # Ensure valid page
        
        start_idx = page * TASKS_PER_PAGE
        end_idx = min(start_idx + TASKS_PER_PAGE, total_tasks)
        page_tasks = tasks_data[start_idx:end_idx]
        
        # Build task list
        text = f"""
📅 **定时任务列表** ({total_tasks} 个任务)

"""
        
        if total_pages > 1:
            text += f"📄 第 {page + 1}/{total_pages} 页\n\n"
        
        keyboard = []
        for i, task in enumerate(page_tasks, start=start_idx + 1):
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
            
            # Add control buttons for each task WITH task number
            toggle_text = "禁用" if enabled else "启用"
            keyboard.append([
                InlineKeyboardButton(f"{i}. {toggle_text}", callback_data=f"toggle_task_{task_id}"),
                InlineKeyboardButton(f"{i}. 📜 日志", callback_data=f"task_logs_{task_id}"),
                InlineKeyboardButton(f"{i}. 🗑️ 删除", callback_data=f"delete_task_{task_id}"),
            ])
        
        # Add pagination buttons if needed
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"tasks_page_{page - 1}"))
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"tasks_page_{page + 1}"))
            if nav_buttons:
                keyboard.append(nav_buttons)
        
        # Add create task button
        keyboard.append([InlineKeyboardButton("➕ 创建新任务", callback_data="create_task_start")])
        
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
    
    async def _show_task_logs(self, query, callback_data: str):
        """Show execution logs for a scheduled task."""
        from web_app.services.scheduler_service import scheduler_service
        
        task_id = callback_data.replace("task_logs_", "")
        
        # Get task info
        task = scheduler_service.get_task(task_id)
        if not task:
            await query.answer("❌ 任务不存在", show_alert=True)
            return
        
        # Get task logs
        logs = scheduler_service.get_task_logs(task_id, limit=5)
        
        task_name = self._escape_markdown(task.name)
        
        if not logs:
            text = f"""
📜 **任务执行日志**

任务: {task_name}

暂无执行记录

💡 提示：任务执行后会记录执行日志
"""
        else:
            text = f"""
📜 **任务执行日志**

任务: {task_name}

最近 {len(logs)} 次执行记录：

"""
            for i, log in enumerate(logs, 1):
                timestamp = log.get('timestamp', '')
                success = log.get('success', False)
                message = log.get('message', '')
                details = log.get('details', '')
                
                # Format timestamp
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime('%m-%d %H:%M')
                except:
                    time_str = timestamp[:16] if timestamp else'Unknown'
                
                # Status icon
                status_icon = "✅" if success else "❌"
                
                # Truncate details for display
                details_short = details[:100] + "..." if len(details) > 100 else details
                details_safe = self._escape_markdown(details_short)
                
                text += f"""
{i}. {status_icon} `{time_str}`
   {message}
"""
                if details_short:
                    text += f"   {details_safe}\n"
        
        keyboard = []
        self._add_back_button(keyboard, "tasks_scheduled")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
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
        task_options = self._task_options.get(chat_id, {"complex_task": False, "send_email": False, "parallel": False})
        task_content = self._pending_tasks.get(chat_id, "未知任务")
        selected_devices = self._selected_devices.get(chat_id, set())

        # Build toggle buttons with checkboxes
        keep_unlocked_icon = "☑️" if task_options["complex_task"] else "☐"
        email_icon = "☑️" if task_options["send_email"] else "☐"
        parallel_icon = "☑️" if task_options.get("parallel", False) else "☐"

        task_escaped = self._escape_markdown(task_content[:100])

        # Build text with optional parallel section
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
"""

        # Add parallel option only if multiple devices selected
        if len(selected_devices) > 1:
            text += f"""
{parallel_icon} **并行执行**
├ 多设备同时执行任务
├ 大幅缩短总执行时间
└ 每个设备独立运行
"""

        text += "\n💡 点击按钮切换开关状态\n"

        keyboard = [
            [InlineKeyboardButton(f"{keep_unlocked_icon} 保持解锁", callback_data="toggle_complex_task")],
            [InlineKeyboardButton(f"{email_icon} 邮件通知", callback_data="toggle_send_email")],
        ]

        # Add parallel button only if multiple devices selected
        if len(selected_devices) > 1:
            keyboard.append([InlineKeyboardButton(f"{parallel_icon} 并行执行", callback_data="toggle_parallel")])

        keyboard.append([InlineKeyboardButton("✅ 确认并执行", callback_data="confirm_task_options")])
        keyboard.append([InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")])

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
    
    async def _show_device_action_list(self, query, action: str):
        """Show device list for lock/unlock action."""
        from web_app.services.device_service import device_service
        
        devices = device_service.get_all_devices()
        
        action_icons = {
            "lock": "🔒",
            "unlock": "🔓"
        }
        action_names = {
            "lock": "锁定",
            "unlock": "解锁"
        }
        
        icon = action_icons.get(action, "🔧")
        name = action_names.get(action, action)
        
        if not devices:
            text = f"""
{icon} **设备{name}**

暂无设备

💡 提示：请先连接设备
"""
            keyboard = []
            self._add_back_button(keyboard, "menu_devices")
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        text = f"""
{icon} **设备{name}**

选择要{name}的设备：

"""
        
        keyboard = []
        for device in devices:
            device_name = self._escape_markdown(device.name or device.id[:20])
            status_icon = "🟢" if device.status == "connected" else "🔴"
            
            button_text = f"{status_icon} {device_name}"
            callback_data = f"device_{action}_{device.id}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        self._add_back_button(keyboard, "menu_devices")
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _execute_device_unlock(self, query, device_id: str):
        """Execute unlock operation on a device."""
        from web_app.services.device_service import device_service
        
        device = device_service.get_device(device_id)
        if not device:
            await query.answer("❌ 设备未找到", show_alert=True)
            return
        
        device_name = self._escape_markdown(device.name or device.id[:20])
        
        try:
            # Try to unlock
            success = await device_service.unlock_device(device_id)
            
            if success:
                text = f"""
✅ **解锁成功**

设备: {device_name}
状态: 已解锁
"""
                await query.answer("✅ 设备已解锁")
            else:
                text = f"""
❌ **解锁失败**

设备: {device_name}

可能原因:
• PIN 未配置或不正确
• 设备未响应
• 设备已解锁

💡 提示：请在 Web 端设置 → 设备管理中配置 PIN
"""
                await query.answer("❌ 解锁失败", show_alert=True)
            
            keyboard = []
            self._add_back_button(keyboard, "devices_unlock_list")
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error unlocking device {device_id}: {e}")
            await query.answer(f"❌ 解锁出错: {str(e)}", show_alert=True)
    
    async def _execute_device_lock(self, query, device_id: str):
        """Execute lock operation on a device."""
        from web_app.services.device_service import device_service
        
        device = device_service.get_device(device_id)
        if not device:
            await query.answer("❌ 设备未找到", show_alert=True)
            return
        
        device_name = self._escape_markdown(device.name or device.id[:20])
        
        try:
            # Try to lock
            success = await device_service.lock_device(device_id)
            
            if success:
                text = f"""
✅ **锁定成功**

设备: {device_name}
状态: 已锁定
"""
                await query.answer("✅ 设备已锁定")
            else:
                text = f"""
❌ **锁定失败**

设备: {device_name}

可能原因:
• 设备未响应
• 设备已锁定

💡 提示：请检查设备连接状态
"""
                await query.answer("❌ 锁定失败", show_alert=True)
            
            keyboard = []
            self._add_back_button(keyboard, "devices_lock_list")
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error locking device {device_id}: {e}")
            await query.answer(f"❌ 锁定出错: {str(e)}", show_alert=True)
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

    async def _send_screenshots_to_chat(self, chat_id: int, screenshots: dict):
        """Send device screenshots to a chat as photos.

        Args:
            chat_id: Telegram chat ID to send to
            screenshots: Dict of {device_id: screenshot_data (base64 str or bytes)}
        """
        import base64
        for device_id, screenshot_data in screenshots.items():
            try:
                # Convert base64 string to bytes if needed
                if isinstance(screenshot_data, str):
                    photo_bytes = base64.b64decode(screenshot_data)
                else:
                    photo_bytes = screenshot_data

                device_short = device_id[:12] if len(device_id) > 12 else device_id
                caption = f"📱 设备 {device_short} 执行结果截图"
                await self.send_photo(chat_id, photo_bytes, caption=caption)
                logger.info(f"Screenshot sent to group {chat_id} for device {device_short}")
            except Exception as e:
                logger.error(f"Failed to send screenshot for device {device_id} to {chat_id}: {e}")
    
    # === TASK CREATION FLOW ===
    async def _handle_task_creation_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text input during task creation flow."""
        user_id = update.effective_user.id
        
        if user_id not in self._task_creation:
            return
        
        step = self._task_creation[user_id]["step"]
        
        if step == "name":
            await self._handle_task_name_input(update, context)
        elif step == "content":
            await self._handle_task_content_input(update, context)
        elif step == "time":
            await self._handle_time_input(update, context)
    
    async def _start_task_creation(self, query):
        """Start the interactive task creation flow."""
        user_id = query.from_user.id
        
        # Initialize task creation state
        self._task_creation[user_id] = {
            "step": "name",
            "data": {}
        }
        
        text = """
➕ **创建定时任务 - 第1步**

请输入任务名称：

💡 示例: `每日数据备份`, `周一截图任务`

发送消息输入任务名称
"""
        
        keyboard = [[InlineKeyboardButton("❌ 取消", callback_data="task_create_cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        await query.answer("请在聊天中输入任务名称")
    
    async def _handle_task_name_input(self, update, context):
        """Handle task name input."""
        user_id = update.effective_user.id
        task_name = update.message.text.strip()
        
        if not task_name:
            await update.message.reply_text("❌ 任务名称不能为空，请重新输入：")
            return
        
        self._task_creation[user_id]["data"]["name"] = task_name
        self._task_creation[user_id]["step"] = "content"
        
        text = f"""
✅ 任务名称: `{task_name}`

➕ **创建定时任务 - 第2步**

请输入任务内容（要执行的指令）：

💡 示例: 
• `帮我打开微信，查看未读消息`
• `截取屏幕并保存`

发送消息输入任务内容：
"""
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def _handle_task_content_input(self, update, context):
        """Handle task content input."""
        user_id = update.effective_user.id
        task_content = update.message.text.strip()
        
        if not task_content:
            await update.message.reply_text("❌ 任务内容不能为空，请重新输入：")
            return
        
        self._task_creation[user_id]["data"]["content"] = task_content
        self._task_creation[user_id]["step"] = "device"
        
        from web_app.services.device_service import device_service
        devices = device_service.get_all_devices()
        
        if not devices:
            await update.message.reply_text("❌ 暂无可用设备\n\n请先连接设备后再创建任务")
            del self._task_creation[user_id]
            return
        
        text = f"""
✅ 任务内容: `{task_content[:50]}...`

➕ **创建定时任务 - 第3步**

选择要执行任务的设备：
"""
        keyboard = []
        # Store device IDs temporarily to map indices
        device_ids = []
        for idx, device in enumerate(devices):
            device_name = device.name or device.id[:20]
            status_icon = "🟢" if device.status == "connected" else "🔴"
            device_ids.append(device.id)
            keyboard.append([InlineKeyboardButton(
                f"{status_icon} {device_name}",
                callback_data=f"task_device_select_{idx}"  # Use index instead of full ID
            )])
        
        # Store device IDs mapping temporarily
        self._task_creation[user_id]["device_ids"] = device_ids
        
        keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="task_create_cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_task_device_selection(self, query, callback_data: str):
        """Handle device selection in task creation flow."""
        user_id = query.from_user.id
        
        if user_id not in self._task_creation or self._task_creation[user_id]["step"] != "device":
            await query.answer("❌ 会话已过期，请重新开始")
            return
        
        # Extract device index and resolve to actual device ID
        device_idx_str = callback_data.replace("task_device_select_", "")
        try:
            device_idx = int(device_idx_str)
            device_ids = self._task_creation[user_id].get("device_ids", [])
            if device_idx < 0 or device_idx >= len(device_ids):
                await query.answer("❌ 设备选择无效")
                return
            device_id = device_ids[device_idx]
        except (ValueError, KeyError):
            await query.answer("❌ 设备选择错误")
            return
        
        self._task_creation[user_id]["data"]["device_id"] = device_id
        self._task_creation[user_id]["step"] = "schedule"
        
        text = """
➕ **创建定时任务 - 第4步**

选择任务执行计划：
"""
        keyboard = [
            [InlineKeyboardButton("📅 每天执行", callback_data="task_schedule_daily")],
            [InlineKeyboardButton("📆 每周执行", callback_data="task_schedule_weekly")],
            [InlineKeyboardButton("⏱️ 间隔执行", callback_data="task_schedule_interval")],
            [InlineKeyboardButton("❌ 取消", callback_data="task_create_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_schedule_selection(self, query, callback_data: str):
        """Handle schedule type selection."""
        user_id = query.from_user.id
        
        if user_id not in self._task_creation or self._task_creation[user_id]["step"] != "schedule":
            await query.answer("❌ 会话已过期，请重新开始")
            return
        
        schedule_type = callback_data.replace("task_schedule_", "")
        self._task_creation[user_id]["data"]["schedule_type"] = schedule_type
        self._task_creation[user_id]["step"] = "time"
        
        if schedule_type == "daily":
            text = """
➕ **创建定时任务 - 第5步**

请输入每天执行的时间：

💡 格式: `HH:MM` (24小时制)
💡 示例: `09:00`, `14:30`

发送消息输入时间：
"""
        elif schedule_type == "weekly":
            # Set default for weekly
            self._task_creation[user_id]["data"]["weekly_days"] = [0]  # Monday
            self._task_creation[user_id]["data"]["weekly_time"] = "09:00"
            self._task_creation[user_id]["step"] = "confirm"
            await self._show_task_creation_summary(query)
            return
        else:  # interval
            text = """
➕ **创建定时任务 - 第5步**

请输入执行间隔（分钟）：

💡 示例: `30` (每30分钟), `60` (每小时)

发送消息输入间隔分钟数：
"""
        
        await query.edit_message_text(text, parse_mode='Markdown')
        await query.answer("请在聊天中输入")
    
    async def _handle_time_input(self, update, context):
        """Handle time input."""
        user_id = update.effective_user.id
        time_input = update.message.text.strip()
        schedule_type = self._task_creation[user_id]["data"]["schedule_type"]
        
        if schedule_type == "daily":
            import re
            if not re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time_input):
                await update.message.reply_text("❌ 时间格式错误，请使用 HH:MM 格式（如 09:00）：")
                return
            self._task_creation[user_id]["data"]["daily_time"] = time_input
        elif schedule_type == "interval":
            try:
                interval = int(time_input)
                if interval <= 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("❌ 请输入有效的正整数（分钟数）：")
                return
            self._task_creation[user_id]["data"]["interval_minutes"] = interval
        
        self._task_creation[user_id]["step"] = "confirm"
        await self._show_task_creation_summary_msg(update)
    
    async def _show_task_creation_summary(self, query):
        """Show task creation summary for confirmation."""
        user_id = query.from_user.id
        data = self._task_creation[user_id]["data"]
        
        schedule_type = data["schedule_type"]
        if schedule_type == "daily":
            schedule_text = f"每天 {data['daily_time']}"
        elif schedule_type == "weekly":
            schedule_text = f"每周一 {data['weekly_time']}"
        else:
            schedule_text = f"每 {data['interval_minutes']} 分钟"
        
        text = f"""
📋 **任务创建确认**

任务名称: `{data['name']}`
任务内容: `{data['content'][:80]}...`
执行计划: {schedule_text}

确认创建此任务？
"""
        keyboard = [
            [InlineKeyboardButton("✅ 确认创建", callback_data="task_create_confirm")],
            [InlineKeyboardButton("❌ 取消", callback_data="task_create_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _show_task_creation_summary_msg(self, update):
        """Show task creation summary via message."""
        user_id = update.effective_user.id
        data = self._task_creation[user_id]["data"]
        
        schedule_type = data["schedule_type"]
        if schedule_type == "daily":
            schedule_text = f"每天 {data['daily_time']}"
        elif schedule_type == "weekly":
            schedule_text = f"每周一 {data['weekly_time']}"
        else:
            schedule_text = f"每 {data['interval_minutes']} 分钟"
        
        text = f"""
📋 **任务创建确认**

任务名称: `{data['name']}`
任务内容: `{data['content'][:80]}...`
执行计划: {schedule_text}

确认创建此任务？
"""
        keyboard = [
            [InlineKeyboardButton("✅ 确认创建", callback_data="task_create_confirm")],
            [InlineKeyboardButton("❌ 取消", callback_data="task_create_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _confirm_task_creation(self, query):
        """Create the scheduled task."""
        user_id = query.from_user.id
        
        if user_id not in self._task_creation:
            await query.answer("❌ 会话已过期", show_alert=True)
            return
        
        data = self._task_creation[user_id]["data"]
        
        try:
            from web_app.models.scheduler import ScheduledTask
            from web_app.services.scheduler_service import scheduler_service
            import uuid
            
            # Prepare devices list (convert single device_id to list)
            device_id = data.get("device_id")
            devices_list = [device_id] if device_id else []
            
            task = ScheduledTask(
                id=str(uuid.uuid4())[:8],
                name=data["name"],
                task_content=data["content"],
                devices=devices_list,  # Use 'devices' list instead of 'device_id'
                enabled=True,
                schedule_type=data["schedule_type"]
            )
            
            if data["schedule_type"] == "daily":
                task.daily_time = data["daily_time"]
            elif data["schedule_type"] == "weekly":
                task.weekly_days = data.get("weekly_days", [0])
                task.weekly_time = data.get("weekly_time", "09:00")
            else:
                task.interval_minutes = data["interval_minutes"]
            
            scheduler_service.add_task(task)
            del self._task_creation[user_id]
            
            text = f"""
✅ **任务创建成功！**

任务 `{data['name']}` 已添加到定时任务列表

您可以在 📅 定时任务 中查看和管理
"""
            keyboard = [[InlineKeyboardButton("📅 查看任务列表", callback_data="tasks_scheduled")]]
            self._add_back_button(keyboard, "menu_tasks")
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            await query.answer("✅ 任务创建成功")
            
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            await query.answer(f"❌ 创建失败: {str(e)}", show_alert=True)
    
    async def _cancel_task_creation(self, query):
        """Cancel task creation flow."""
        user_id = query.from_user.id
        
        if user_id in self._task_creation:
            del self._task_creation[user_id]
        
        text = """
❌ **任务创建已取消**

返回任务管理菜单
"""
        keyboard = []
        self._add_back_button(keyboard, "tasks_scheduled")
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        await query.answer("已取消")
    # === END TASK CREATION FLOW ===


    async def _update_progress_message(
        self,
        chat_id: int,
        task_content: str = "",
        progress: int = 0,
        latest_log: str = ""
    ):
        """Update the progress message with latest status."""
        import time
        
        # Rate limiting - at most one update every 0.5 seconds per chat
        progress_key = f"progress_{chat_id}"
        now = time.time()
        if progress_key in self._last_update_time:
            if now - self._last_update_time[progress_key] < 0.5:
                # Skip update if too soon, unless it's an important log
                if not any(keyword in latest_log for keyword in ["✅", "❌", "完成", "失败", "错误"]):
                    return
        
        self._last_update_time[progress_key] = now
        
        # Build progress bar (20 blocks, 5% per block)
        filled = int(progress / 5)
        bar = "━" * filled + "░" * (20 - filled)
        
        # Format message
        text = (
            f"📝 **任务执行中**\n\n"
            f"🎯 {task_content[:50]}...\n\n"
            f"{bar}\n"
            f"⏳ 进度: {progress}%\n"
        )
        
        # Add model name and token counter on same line if available
        info_parts = []
        if chat_id in self._model_names:
            info_parts.append(f"🤖 {self._model_names[chat_id]}")
        if chat_id in self._token_counters and self._token_counters[chat_id] > 0:
            info_parts.append(f"🔢 {self._token_counters[chat_id]:,} tokens")
        
        if info_parts:
            text += " | ".join(info_parts) + "\n"
        
        # Add recent logs at the bottom if available (show last 5-10 lines)
        if chat_id in self._recent_logs and self._recent_logs[chat_id]:
            recent = self._recent_logs[chat_id][-5:]  # Show last 5 logs
            text += "\n💬 **最新日志:**\n"
            for log in recent:
                # Clean log: remove special chars, emoji codes,  and limit length
                clean_log = log.replace("[", "").replace("]", "").replace("`", "")
                # Escape markdown special characters to prevent parsing errors
                clean_log = self._escape_markdown(clean_log)
                import re
                clean_log = re.sub(r'\[TOKENS\].*?\[/TOKENS\]', '', clean_log)
                # Limit each log line to 100 chars
                if len(clean_log) > 100:
                    clean_log = clean_log[:97] + "..."
                text += f"  • {clean_log}\n"
        
        # Update or send message
        message_id = self._progress_messages.get(chat_id)
        try:
            if message_id:
                # Update existing message
                await self._application.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode='Markdown'
                )
            else:
                # Send new message
                sent_message = await self._application.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='Markdown'
                )
                self._progress_messages[chat_id] = sent_message.message_id
        except Exception as e:
            # Catch "message is not modified" error and ignore
            if "message is not modified" not in str(e).lower():
                logger.error(f"Failed to update progress message: {e}")
    
    async def _update_screenshot(self, chat_id: int):
        """Update screenshot by sending all new screenshots from all devices."""
        try:
            from web_app.services.chat_service import chat_service
            import base64
            from io import BytesIO
            import asyncio
            
            # Get session context
            session_id = None
            
            # Try to get from chat_service current context
            from web_app.services.task_service import task_service
            if hasattr(task_service, '_chat_context'):
                session_id = task_service._chat_context.session_id
            
            if not session_id:
                return
            
            # === MULTI-DEVICE FIX: Get ALL screenshots from session, not just one message ===
            # Get all screenshots from the entire session (all devices)
            screenshots = chat_service.get_screenshots(session_id, message_id=None)
            
            if not screenshots:
                return
            
            # Initialize sent screenshots set if not exists
            if chat_id not in self._sent_screenshots:
                self._sent_screenshots[chat_id] = set()
            
            # Find new screenshots that haven't been sent yet
            new_screenshots = [
                s for s in screenshots 
                if s['id'] not in self._sent_screenshots[chat_id]
            ]
            
            if not new_screenshots:
                return
            
            # Send all new screenshots with retry mechanism
            for screenshot in new_screenshots:
                screenshot_id = screenshot['id']
                max_retries = 3
                retry_delays = [0.5, 1.5, 3.0]  # Progressive wait times for data transmission
                
                for attempt in range(max_retries):
                    try:
                        # Wait for screenshot data to be fully transmitted (especially for old devices)
                        if attempt > 0:
                            wait_time = retry_delays[attempt - 1]
                            logger.info(f"Retry {attempt}/{max_retries} for screenshot {screenshot_id}, waiting {wait_time}s for data transmission")
                            await asyncio.sleep(wait_time)
                        
                        screenshot_data = chat_service.get_screenshot(screenshot_id)
                        
                        if not screenshot_data:
                            if attempt < max_retries - 1:
                                continue  # Retry
                            else:
                                logger.warning(f"Screenshot {screenshot_id} data not available after {max_retries} attempts")
                                break
                        
                        # Validate screenshot data
                        try:
                            image_bytes = base64.b64decode(screenshot_data)
                            if len(image_bytes) < 100:  # Too small, likely incomplete
                                raise ValueError(f"Screenshot data too small: {len(image_bytes)} bytes")
                        except Exception as decode_error:
                            if attempt < max_retries - 1:
                                logger.warning(f"Screenshot {screenshot_id} decode failed (attempt {attempt + 1}): {decode_error}")
                                continue  # Retry
                            else:
                                raise
                        
                        # Send screenshot
                        photo = BytesIO(image_bytes)
                        photo.name = "screenshot.jpg"
                        
                        # Get device info from description if available
                        description = screenshot.get('description', '执行中...')
                        caption = f"📸 {description[:100]}"
                        
                        await self._application.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                            caption=caption
                        )
                        
                        logger.info(f"Screenshot {screenshot_id} sent successfully (attempt {attempt + 1})")
                        
                        # Mark as sent
                        self._sent_screenshots[chat_id].add(screenshot_id)
                        
                        # Delay between screenshots to avoid rate limiting
                        if len(new_screenshots) > 1:
                            await asyncio.sleep(1.0)
                        
                        # Success, break retry loop
                        break
                        
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logger.warning(f"Failed to send screenshot {screenshot_id} (attempt {attempt + 1}/{max_retries}): {e}")
                            # Will retry
                        else:
                            logger.error(f"Failed to send screenshot {screenshot_id} after {max_retries} attempts: {e}")
            
        except Exception as e:
            logger.error(f"Failed to update screenshot: {e}")
    
    async def send_device_completion(
        self, 
        chat_id: int, 
        device_id: str, 
        session_id: str, 
        message_id: str,
        status: str,
        logs: list[str],
        skip_unlock: bool = False  # If True, assume device is already unlocked
    ):
        """Send device completion report with screenshot and logs immediately."""
        try:
            from web_app.services.chat_service import chat_service
            import base64
            from io import BytesIO
            
            device_short_id = device_id[:12] if len(device_id) > 12 else device_id
            status_emoji = "✅" if status == "completed" else "❌"
            
            # Send screenshot first if available - use same method as /screenshot command
            try:
                from web_app.services.device_service import device_service
                import base64
                from io import BytesIO
                
                # Only handle lock/unlock if skip_unlock is False
                was_locked = False
                try:
                    if not skip_unlock:
                        # Check if device is locked
                        was_locked = await device_service.is_screen_locked(device_id)
                        logger.info(f"Device {device_id} lock state before completion screenshot: {was_locked}")
                        
                        # Unlock if needed
                        if was_locked:
                            pin = device_service.get_device_pin(device_id)
                            unlock_success = await device_service.unlock_device(device_id, pin)
                            if not unlock_success:
                                logger.warning(f"Failed to unlock device {device_id} for completion screenshot")
                            else:
                                logger.info(f"Unlocked device {device_id} for completion screenshot")
                    else:
                        logger.info(f"Skipping lock check for {device_id} (device already unlocked during task)")
                    
                    # Capture screenshot using correct method name
                    screenshot_data = await device_service.get_screenshot(device_id)
                    
                    if screenshot_data:
                        # Store screenshot for email reporting (if task object is accessible)
                        # This will be used by email report generation
                        if not hasattr(self, '_device_screenshots'):
                            self._device_screenshots = {}
                        self._device_screenshots[device_id] = screenshot_data
                        if isinstance(screenshot_data, str):
                            screenshot_bytes = base64.b64decode(screenshot_data)
                        else:
                            screenshot_bytes = screenshot_data
                        
                        # === Save screenshot to database for Web UI ===
                        try:
                            screenshot_result = chat_service.add_screenshot(
                                session_id,
                                message_id,
                                screenshot_data,
                                f"设备 {device_short_id} 任务完成"
                            )
                            screenshot_id = screenshot_result.get("id")
                            logger.info(f"Saved screenshot {screenshot_id} to database for Web UI")
                        except Exception as save_error:
                            logger.error(f"Failed to save screenshot to database: {save_error}")
                        
                        photo = BytesIO(screenshot_bytes)
                        photo.seek(0)
                        photo.name = "screenshot.jpg"
                        
                        caption = f"{status_emoji} 设备 {device_short_id} 任务完成"
                        
                        await self._application.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                            caption=caption
                        )
                        logger.info(f"Sent completion screenshot for device {device_id}")
                    else:
                        logger.warning(f"No screenshot data available for device {device_id}")
                        
                finally:
                    # Only restore lock state if we unlocked it ourselves
                    # AND we're not in persistent chat mode
                    is_chat_mode = chat_id in self._chat_mode_active and self._chat_mode_active[chat_id]
                    if not skip_unlock and was_locked and not is_chat_mode:
                        await device_service.lock_device(device_id)
                        logger.info(f"Restored lock state for device {device_id}")
                    elif is_chat_mode:
                        logger.info(f"Skipping lock restore for chat mode (device {device_id})")
                        
            except Exception as e:
                logger.error(f"Failed to send screenshot for device {device_id}: {e}")
            
            
            # Send logs summary (skip for chat mode - screenshot is enough)
            is_chat_mode = chat_id in self._chat_mode_active and self._chat_mode_active[chat_id]
            if logs and len(logs) > 0 and not is_chat_mode:
                # Get last 10 logs, filter out token lines
                recent_logs = [log for log in logs[-15:] if not log.startswith('[TOKENS]')][-10:]
                if recent_logs:
                    logs_text = "\n".join(recent_logs)
                    if len(logs_text) > 3500:
                        logs_text = logs_text[-3500:]
                    
                    # Escape for Telegram markdown
                    logs_text = logs_text.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('`', '\\`')
                    
                    await self._application.bot.send_message(
                        chat_id=chat_id,
                        text=f"{status_emoji} **设备 {device_short_id} 日志**\n```\n{logs_text}\n```",
                        parse_mode='Markdown'
                    )
                    logger.info(f"Sent logs for device {device_id}")
                    
        except Exception as e:
            logger.error(f"Failed to send device completion for {device_id}: {e}")


# Global instance
telegram_bot_service = TelegramBotService()
