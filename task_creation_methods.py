# Task Creation Helper Functions

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

发送消息输入任务名称，或使用 /cancel 取消创建
"""
    
    keyboard = [[InlineKeyboardButton("❌ 取消", callback_data="task_create_cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    await query.answer("请在聊天中输入任务名称")


async def _handle_task_name_input(self, update, context):
    """Handle task name input in task creation flow."""
    user_id = update.effective_user.id
    
    if user_id not in self._task_creation or self._task_creation[user_id]["step"] != "name":
        return
    
    task_name = update.message.text.strip()
    
    if not task_name:
        await update.message.reply_text("❌ 任务名称不能为空，请重新输入：")
        return
    
    # Save name and move to content step
    self._task_creation[user_id]["data"]["name"] = task_name
    self._task_creation[user_id]["step"] = "content"
    
    text = f"""
✅ 任务名称: `{task_name}`

➕ **创建定时任务 - 第2步**

请输入任务内容（要执行的指令）：

💡 示例: 
• `帮我打开微信，查看未读消息`
• `截取屏幕并保存`
• `备份应用数据`

发送消息输入任务内容：
"""
    
    await update.message.reply_text(text, parse_mode='Markdown')


async def _handle_task_content_input(self, update, context):
    """Handle task content input in task creation flow."""
    user_id = update.effective_user.id
    
    if user_id not in self._task_creation or self._task_creation[user_id]["step"] != "content":
        return
    
    task_content = update.message.text.strip()
    
    if not task_content:
        await update.message.reply_text("❌ 任务内容不能为空，请重新输入：")
        return
    
    # Save content and move to device selection
    self._task_creation[user_id]["data"]["content"] = task_content
    self._task_creation[user_id]["step"] = "device"
    
    # Show device selection
    from web_app.services.device_service import device_service
    devices = device_service.get_all_devices()
    
    if not devices:
        await update.message.reply_text(
            "❌ 暂无可用设备\n\n请先连接设备后再创建任务",
            parse_mode='Markdown'
        )
        del self._task_creation[user_id]
        return
    
    text = f"""
✅ 任务内容: `{task_content[:50]}...`

➕ **创建定时任务 - 第3步**

选择要执行任务的设备：
"""
    
    keyboard = []
    for device in devices:
        device_name = device.name or device.id[:20]
        status_icon = "🟢" if device.status == "connected" else "🔴"
        keyboard.append([InlineKeyboardButton(
            f"{status_icon} {device_name}",
            callback_data=f"task_device_select_{device.id}"
        )])
    
    keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="task_create_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def _handle_task_device_selection(self, query, callback_data: str):
    """Handle device selection in task creation flow."""
    user_id = query.from_user.id
    
    if user_id not in self._task_creation or self._task_creation[user_id]["step"] != "device":
        await query.answer("❌ 会话已过期，请重新开始")
        return
    
    device_id = callback_data.replace("task_device_select_", "")
    
    # Save device and move to schedule selection
    self._task_creation[user_id]["data"]["device_id"] = device_id
    self._task_creation[user_id]["step"] = "schedule"
    
    text = f"""
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
    """Handle schedule type selection in task creation flow."""
    user_id = query.from_user.id
    
    if user_id not in self._task_creation or self._task_creation[user_id]["step"] != "schedule":
        await query.answer("❌ 会话已过期，请重新开始")
        return
    
    schedule_type = callback_data.replace("task_schedule_", "")
    
    # Save schedule type and move to time input
    self._task_creation[user_id]["data"]["schedule_type"] = schedule_type
    self._task_creation[user_id]["step"] = "time"
    
    if schedule_type == "daily":
        text = """
➕ **创建定时任务 - 第5步**

请输入每天执行的时间：

💡 格式: `HH:MM` (24小时制)
💡 示例: `09:00`, `14:30`, `20:00`

发送消息输入时间：
"""
    elif schedule_type == "weekly":
        text = """
➕ **创建定时任务 - 第5步**

暂时使用默认设置：每周一 09:00 执行

点击"确认创建"完成任务创建
"""
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

💡 示例: `30` (每30分钟), `60` (每小时), `120` (每2小时)

发送消息输入间隔分钟数：
"""
    
    await query.edit_message_text(text, parse_mode='Markdown')
    await query.answer("请在聊天中输入")


async def _handle_time_input(self, update, context):
    """Handle time input in task creation flow."""
    user_id = update.effective_user.id
   
    if user_id not in self._task_creation or self._task_creation[user_id]["step"] != "time":
        return
    
    time_input = update.message.text.strip()
    schedule_type = self._task_creation[user_id]["data"]["schedule_type"]
    
    if schedule_type == "daily":
        # Validate time format
        import re
        if not re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time_input):
            await update.message.reply_text("❌ 时间格式错误，请使用 HH:MM 格式（如 09:00）：")
            return
        
        self._task_creation[user_id]["data"]["daily_time"] = time_input
    
    elif schedule_type == "interval":
        # Validate interval
        try:
            interval = int(time_input)
            if interval <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ 请输入有效的正整数（分钟数）：")
            return
        
        self._task_creation[user_id]["data"]["interval_minutes"] = interval
    
    # Move to confirmation
    self._task_creation[user_id]["step"] = "confirm"
    
    # Show summary
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
        from gui_app.scheduler import ScheduledTask, ScheduleType
        from web_app.services.scheduler_service import scheduler_service
        import uuid
        
        # Create task object
        task = ScheduledTask(
            id=str(uuid.uuid4())[:8],
            name=data["name"],
            task_content=data["content"],
            device_id=data.get("device_id"),
            enabled=True,
            schedule_type=data["schedule_type"]
        )
        
        # Set schedule parameters
        if data["schedule_type"] == "daily":
            task.daily_time = data["daily_time"]
        elif data["schedule_type"] == "weekly":
            task.weekly_days = data.get("weekly_days", [0])
            task.weekly_time = data.get("weekly_time", "09:00")
        else:  # interval
            task.interval_minutes = data["interval_minutes"]
        
        # Add task
        task_id = scheduler_service.add_task(task)
        
        # Clear state
        del self._task_creation[user_id]
        
        text = f"""
✅ **任务创建成功！**

任务 `{data['name']}` 已添加到定时任务列表

您可以在 📅 定时任务 中查看和管理
"""
        
        keyboard = []
        keyboard.append([InlineKeyboardButton("📅 查看任务列表", callback_data="tasks_scheduled")])
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
