# -*- coding: utf-8 -*-
"""
Tasks API router.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import logging

from web_app.auth import verify_token
from web_app.services.task_service import task_service

# 设置详细日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# 确保有控制台输出
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _normalize_openai_like_base_url(base_url: str, protocol: str) -> str:
    """Normalize OpenAI-compatible base URL for provider-specific quirks."""
    normalized = (base_url or "").rstrip("/")
    if protocol == "ollama" and normalized and not normalized.endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


class RunTaskRequest(BaseModel):
    task_content: str
    device_ids: list[str]
    model_settings: Optional[dict] = None
    send_email: Optional[bool] = True  # Default True for backward compatibility
    no_auto_lock: Optional[bool] = False  # 复杂任务模式下不自动锁屏
    restore_lock_to_state: Optional[bool] = None  # 明确指定要恢复的锁屏状态（用于子任务链）
    task_type: Optional[str] = "manual"  # 任务类型: chat/scheduled/manual
    force_run: Optional[bool] = False  # 是否强制执行（打断当前任务）
    session_id: Optional[str] = None  # 聊天会话 ID（用于在同一会话中发送多个消息）
    message_id: Optional[str] = None  # 消息 ID（用于绑定日志和截图）
    debug_mode: Optional[bool] = False  # 调试模式：点击前显示预览
    parallel: Optional[bool] = False  # 多设备并行执行模式


class DecomposeTaskRequest(BaseModel):
    task_content: str


class TaskResponse(BaseModel):
    id: str
    task_content: str
    device_ids: list[str]
    status: str
    start_time: str
    end_time: str = ""
    results: list = []
    logs: list = []
    progress: int = 0
    initial_lock_state: Optional[bool] = None  # Initial lock state detected (for subtask chains)


class TaskStatusResponse(BaseModel):
    running: bool
    task: Optional[TaskResponse] = None


@router.post("/decompose")
async def decompose_task(
    request: DecomposeTaskRequest,
    _: bool = Depends(verify_token)
):
    """
    将复杂任务拆解成todolist。
    使用当前激活的模型服务进行任务拆解。
    """
    from web_app.services.model_service import model_service
    from openai import OpenAI
    import json

    active_model = model_service.get_active_service()
    if not active_model:
        raise HTTPException(status_code=400, detail="No active model service configured")

    # 构建任务拆解的提示词
    decompose_prompt = f"""你是一个任务分解专家。请将用户的复杂任务拆解成一系列可以在手机上逐步执行的简单子任务。

用户的任务: {request.task_content}

请将任务拆解成一个JSON格式的待办清单，每个子任务应该是一个独立可执行的手机操作指令。

**严格按以下JSON格式返回，不要有任何其他文字：**
{{
    "todoList": [
        {{"content": "子任务1的具体操作指令"}},
        {{"content": "子任务2的具体操作指令"}},
        {{"content": "子任务3的具体操作指令"}}
    ]
}}

注意：
1. 每个子任务应该是具体、可执行的手机操作，例如"打开微信"、"点击搜索框"、"输入XXX"等
2. 子任务数量一般在3-10个之间
3. 确保任务按正确的执行顺序排列
4. 只返回JSON，不要有任何解释文字"""

    try:
        # 根据协议类型使用不同的客户端
        logger.info("=" * 80)
        logger.info("[任务拆解] 开始请求模型...")
        logger.info(f"[请求配置] base_url: {active_model.base_url}")
        logger.info(f"[请求配置] model_name: {active_model.model_name}")
        logger.info(f"[请求配置] protocol: {active_model.protocol}")
        logger.info(f"[请求配置] api_key: {active_model.api_key[:10]}...{active_model.api_key[-4:]}" if active_model.api_key else "[请求配置] api_key: None")
        logger.info("-" * 40)
        logger.info(f"[请求提示词]\n{decompose_prompt}")
        logger.info("-" * 40)

        protocol = (active_model.protocol or "openai").lower()
        content = ""
        tokens = 0

        if protocol == "gemini":
            # 使用 Gemini SDK
            try:
                import google.generativeai as genai
            except ImportError:
                raise HTTPException(status_code=500, detail="google-generativeai package not installed")

            base_url = active_model.base_url.rstrip('/') if active_model.base_url else ""
            if base_url.endswith('/v1'):
                base_url = base_url[:-3]
            is_official = not base_url or "googleapis.com" in base_url

            if is_official:
                genai.configure(api_key=active_model.api_key)
            else:
                genai.configure(
                    api_key=active_model.api_key,
                    transport='rest',
                    client_options={'api_endpoint': base_url}
                )

            logger.info("[API调用] 正在发送请求到 Gemini 模型...")
            model = genai.GenerativeModel(active_model.model_name)
            response = model.generate_content(decompose_prompt)
            content = response.text if response.text else ""
            logger.info("[API调用] 收到 Gemini 响应")

        elif protocol == "anthropic":
            # 使用 Anthropic SDK
            try:
                import anthropic
            except ImportError:
                raise HTTPException(status_code=500, detail="anthropic package not installed")

            base_url = active_model.base_url.rstrip('/')
            if base_url.endswith('/messages'):
                base_url = base_url[:-9]

            client = anthropic.Anthropic(
                api_key=active_model.api_key or "EMPTY",
                base_url=base_url,
            )

            logger.info("[API调用] 正在发送请求到 Anthropic 模型...")
            response = client.messages.create(
                model=active_model.model_name,
                max_tokens=2000,
                messages=[{"role": "user", "content": decompose_prompt}],
            )
            content = response.content[0].text if response.content else ""
            tokens = response.usage.input_tokens + response.usage.output_tokens if response.usage else 0
            logger.info("[API调用] 收到 Anthropic 响应")

        else:
            # 默认使用 OpenAI 兼容协议（包含 Ollama）
            normalized_base_url = _normalize_openai_like_base_url(active_model.base_url, protocol)
            if protocol == "ollama":
                api_key = active_model.api_key or "ollama"
            else:
                api_key = active_model.api_key or "EMPTY"
            client = OpenAI(
                base_url=normalized_base_url or active_model.base_url,
                api_key=api_key,
            )

            logger.info("[API调用] 正在发送请求到模型...")
            response = client.chat.completions.create(
                model=active_model.model_name,
                messages=[{"role": "user", "content": decompose_prompt}],
                max_tokens=2000,
                temperature=0.3,
            )
            content = response.choices[0].message.content if response.choices else ""
            tokens = response.usage.total_tokens if response.usage else 0
            logger.info("[API调用] 收到模型响应")

        logger.info("-" * 40)
        logger.info(f"[响应原始内容] (长度: {len(content)})")
        logger.info(content)
        logger.info("-" * 40)
        logger.info(f"[Token使用量] {tokens}")

        # 解析JSON
        try:
            # 尝试直接解析
            logger.info("[解析] 尝试直接解析JSON...")
            result = json.loads(content)
            logger.info("[解析] 直接解析成功!")
        except json.JSONDecodeError as parse_error:
            logger.warning(f"[解析] 直接解析失败: {parse_error}")
            # 尝试从markdown代码块中提取
            import re
            logger.info("[解析] 尝试从markdown代码块提取...")
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if json_match:
                extracted = json_match.group(1)
                logger.info(f"[解析] 从代码块提取内容: {extracted[:200]}...")
                result = json.loads(extracted)
                logger.info("[解析] 代码块解析成功!")
            else:
                # 尝试找到 { 开始的内容
                logger.info("[解析] 尝试查找 {{...}} 结构...")
                start = content.find('{')
                end = content.rfind('}')
                logger.info(f"[解析] 找到位置: start={start}, end={end}")
                if start != -1 and end != -1:
                    json_str = content[start:end+1]
                    logger.info(f"[解析] 提取的JSON字符串: {json_str[:500]}...")
                    result = json.loads(json_str)
                    logger.info("[解析] JSON解析成功!")
                else:
                    logger.error("[解析失败] 无法找到有效的JSON结构!")
                    logger.error(f"[解析失败] 完整响应内容:\n{content}")
                    raise HTTPException(status_code=500, detail="Failed to parse todoList from model response")

        todo_list = result.get("todoList", [])
        logger.info(f"[结果] 解析到 {len(todo_list)} 个子任务")
        for i, item in enumerate(todo_list):
            logger.info(f"  [{i+1}] {item.get('content', item)}")

        if not todo_list:
            logger.error("[错误] todoList 为空!")
            raise HTTPException(status_code=500, detail="Empty todoList returned")

        logger.info("[任务拆解] 完成!")
        logger.info("=" * 80)

        return {
            "success": True,
            "todoList": todo_list,
            "tokens": tokens
        }

    except json.JSONDecodeError as e:
        logger.error(f"[JSON解析错误] {str(e)}")
        logger.error(f"[JSON解析错误] 原始内容: {content if 'content' in dir() else 'N/A'}")
        raise HTTPException(status_code=500, detail=f"Failed to parse model response: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API错误] 类型: {type(e).__name__}")
        logger.error(f"[API错误] 详情: {str(e)}")
        import traceback
        logger.error(f"[API错误] 堆栈:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Model API error: {str(e)}")


@router.post("/run")
async def run_task(
    request: RunTaskRequest,
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_token)
):
    """
    Run a task on specified devices.

    This starts the task in the background and returns immediately.
    Use /api/tasks/status to check progress or connect via WebSocket for real-time updates.
    """
    task_type = request.task_type or "manual"
    force_run = request.force_run or False

    # Check if a task is already running
    current = task_service.get_current_task()
    if current:
        # 检查优先级
        can_interrupt, current_info = task_service.can_interrupt_current_task(task_type)

        if not force_run:
            # 返回冲突信息，让前端决定是否强制执行
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "A task is already running",
                    "can_interrupt": can_interrupt,
                    "current_task": current_info,
                    "new_task_type": task_type,
                }
            )
        else:
            # 强制执行：先停止当前任务
            if can_interrupt:
                logger.info(f"Force stopping current task {current.id} for higher priority task")
                await task_service.stop_all_tasks()
                # 等待任务停止
                import asyncio
                await asyncio.sleep(1)
            else:
                # 不能打断（新任务优先级不够高）
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Cannot interrupt: new task has lower or equal priority",
                        "can_interrupt": False,
                        "current_task": current_info,
                        "new_task_type": task_type,
                    }
                )

    if not request.device_ids:
        raise HTTPException(status_code=400, detail="No devices specified")

    # Start task in background
    async def run_in_background():
        try:
            # Choose parallel or serial execution based on request
            use_parallel = request.parallel and len(request.device_ids) > 1
            
            if use_parallel:
                logger.info(f"[PARALLEL MODE] Running task on {len(request.device_ids)} devices in parallel")
                result = await task_service.run_task_parallel(
                    task_content=request.task_content,
                    device_ids=request.device_ids,
                    model_config=request.model_settings,
                    send_email=request.send_email if request.send_email is not None else True,
                    no_auto_lock=request.no_auto_lock if request.no_auto_lock is not None else False,
                    restore_lock_to_state=request.restore_lock_to_state,
                    task_type=task_type,
                    session_id=request.session_id,
                    debug_mode=request.debug_mode if request.debug_mode is not None else False,
                )
            else:
                result = await task_service.run_task(
                    task_content=request.task_content,
                    device_ids=request.device_ids,
                    model_config=request.model_settings,
                    send_email=request.send_email if request.send_email is not None else True,
                    no_auto_lock=request.no_auto_lock if request.no_auto_lock is not None else False,
                    restore_lock_to_state=request.restore_lock_to_state,
                    task_type=task_type,
                    session_id=request.session_id,
                    message_id=request.message_id,
                    debug_mode=request.debug_mode if request.debug_mode is not None else False,
                )
            # Note: task_finished is already broadcast via _emit_finished callback in task_service
            # No need to call broadcast_task_finished here again
        except Exception as e:
            # Broadcast error only if task_service didn't handle it
            from web_app.routers.websocket import broadcast_task_finished
            await broadcast_task_finished("", False, f"Task failed: {str(e)}", None)

    background_tasks.add_task(run_in_background)

    return {
        "success": True,
        "message": "Task started",
        "task_content": request.task_content,
        "device_ids": request.device_ids,
        "task_type": task_type,
    }


@router.post("/stop")
async def stop_tasks(_: bool = Depends(verify_token)):
    """Stop all running tasks."""
    success = await task_service.stop_all_tasks()
    return {"success": success, "message": "Stop signal sent"}


@router.get("/status", response_model=TaskStatusResponse)
async def get_task_status(_: bool = Depends(verify_token)):
    """Get current task status."""
    status = task_service.get_task_status()
    return TaskStatusResponse(
        running=status["running"],
        task=TaskResponse(**status["task"]) if status["task"] else None
    )


@router.get("/history")
async def get_task_history(
    limit: int = 10,
    _: bool = Depends(verify_token)
):
    """Get recent task history."""
    history = task_service.get_task_history(limit)
    return {"tasks": history}


class ComplexTaskEmailRequest(BaseModel):
    task_name: str
    subtasks: list[dict]  # [{content: str, status: str, logs: list}]
    total_tokens: int = 0
    screenshot_id: Optional[str] = None  # 使用 screenshot_id 而不是 base64


@router.post("/send-complex-email")
async def send_complex_task_email(
    request: ComplexTaskEmailRequest,
    _: bool = Depends(verify_token)
):
    """Send email report for complex task completion."""
    from web_app.services.email_service import email_service

    # Build details from subtasks
    details_lines = []
    success_count = 0
    failed_count = 0

    for i, subtask in enumerate(request.subtasks, 1):
        status_icon = "✅" if subtask.get("status") == "completed" else "❌"
        details_lines.append(f"{status_icon} 子任务 {i}: {subtask.get('content', '')}")
        if subtask.get("logs"):
            for log in subtask["logs"][-3:]:  # Only last 3 logs per subtask
                details_lines.append(f"    {log}")
        if subtask.get("status") == "completed":
            success_count += 1
        else:
            failed_count += 1

    if request.total_tokens > 0:
        details_lines.append(f"\n📊 总Token消耗: {request.total_tokens}")

    details = "\n".join(details_lines)

    # 从数据库获取截图数据（如果提供了 screenshot_id）
    screenshot_data = None
    if request.screenshot_id:
        try:
            from web_app.services.chat_service import chat_service
            screenshot_data = chat_service.get_screenshot(request.screenshot_id)
        except Exception as e:
            logger.error(f"Failed to get screenshot {request.screenshot_id}: {e}")

    success, message = email_service.send_task_report(
        task_name=f"[复杂任务] {request.task_name[:40]}",
        success_count=success_count,
        failed_count=failed_count,
        total_count=len(request.subtasks),
        details=details,
        screenshot_data=screenshot_data,
        is_scheduled=False
    )

    return {"success": success, "message": message}
