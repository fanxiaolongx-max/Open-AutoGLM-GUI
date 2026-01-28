"""Main PhoneAgent class for orchestrating phone automation."""

import json
import logging
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from phone_agent.actions import ActionHandler
from phone_agent.actions.handler import do, finish, parse_action
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.device_factory import get_device_factory
from phone_agent.model import ModelClient, ModelConfig
from phone_agent.model.client import MessageBuilder

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the PhoneAgent."""

    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True
    debug_mode: bool = False  # Enable tap preview before execution

    def __post_init__(self):
        if self.system_prompt is None:
            self.system_prompt = get_system_prompt(self.lang)


@dataclass
class StepResult:
    """Result of a single agent step."""

    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
    message: str | None = None


class PhoneAgent:
    """
    AI-powered agent for automating Android phone interactions.

    The agent uses a vision-language model to understand screen content
    and decide on actions to complete user tasks.

    Args:
        model_config: Configuration for the AI model.
        agent_config: Configuration for the agent behavior.
        confirmation_callback: Optional callback for sensitive action confirmation.
        takeover_callback: Optional callback for takeover requests.

    Example:
        >>> from phone_agent import PhoneAgent
        >>> from phone_agent.model import ModelConfig
        >>>
        >>> model_config = ModelConfig(base_url="http://localhost:8000/v1")
        >>> agent = PhoneAgent(model_config)
        >>> agent.run("Open WeChat and send a message to John")
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: AgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
        tap_preview_callback: Callable[[int, int, int, int, str], tuple[bool, int, int]] | None = None,
    ):
        self.model_config = model_config or ModelConfig()
        self.agent_config = agent_config or AgentConfig()

        self.model_client = ModelClient(self.model_config)
        self.action_handler = ActionHandler(
            device_id=self.agent_config.device_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
            tap_preview_callback=tap_preview_callback if self.agent_config.debug_mode else None,
        )

        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._stop_requested = False  # Stop flag for graceful termination
        self._action_history: list[str] = []  # Track recent actions for loop detection
        self._max_action_history = 10  # Keep last N actions
        self._loop_detected_count = 0  # Count consecutive loop detections
        self._max_loops_before_terminate = 2  # Terminate after this many loop detections

    def request_stop(self) -> None:
        """Request the agent to stop at the next step."""
        self._stop_requested = True

    def is_stop_requested(self) -> bool:
        """Check if stop has been requested."""
        return self._stop_requested

    def run(self, task: str) -> str:
        """
        Run the agent to complete a task.

        Args:
            task: Natural language description of the task.

        Returns:
            Final message from the agent.
        """
        self._context = []
        self._step_count = 0
        self._stop_requested = False  # Reset stop flag

        # Set up ADB keyboard once at task start
        self.action_handler.setup_keyboard()

        try:
            # Check stop before first step
            if self._stop_requested:
                return "Task stopped by user"

            # First step with user prompt
            result = self._execute_step(task, is_first=True)

            if result.finished:
                return result.message or "Task completed"

            # Continue until finished or max steps reached
            while not result.finished and self._step_count < self.agent_config.max_steps:
                # Check stop flag before each step
                if self._stop_requested:
                    print("\n⏹️ Task stopped by user")
                    return "Task stopped by user"

                result = self._execute_step(is_first=False)

            if result.finished:
                return result.message or "Task completed"

            return "Max steps reached"
        finally:
            # Restore original keyboard when task ends
            self.action_handler.restore_keyboard()

    def step(self, task: str | None = None) -> StepResult:
        """
        Execute a single step of the agent.

        Useful for manual control or debugging.

        Args:
            task: Task description (only needed for first step).

        Returns:
            StepResult with step details.
        """
        is_first = len(self._context) == 0

        if is_first and not task:
            raise ValueError("Task is required for the first step")

        # Set up keyboard on first step
        if is_first:
            self.action_handler.setup_keyboard()

        result = self._execute_step(task, is_first)

        # Restore keyboard when task finishes
        if result.finished:
            self.action_handler.restore_keyboard()

        return result

    def cleanup(self) -> None:
        """Clean up resources. Call this when task is cancelled or interrupted."""
        self.action_handler.restore_keyboard()

    def reset(self) -> None:
        """Reset the agent state for a new task."""
        self._context = []
        self._step_count = 0

    def _execute_step(
        self, user_prompt: str | None = None, is_first: bool = False
    ) -> StepResult:
        """Execute a single step of the agent loop."""
        self._step_count += 1

        # Capture current screen state
        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot(self.agent_config.device_id)
        current_app = device_factory.get_current_app(self.agent_config.device_id)

        # Build messages
        if is_first:
            self._context.append(
                MessageBuilder.create_system_message(self.agent_config.system_prompt)
            )

            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"{user_prompt}\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )
        else:
            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"** Screen Info **\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )

        # Get model response with retry for empty responses
        max_retries = 2  # 最多重试2次
        response = None

        for attempt in range(max_retries + 1):
            try:
                msgs = get_messages(self.agent_config.lang)
                if attempt > 0:
                    print(f"\n⚠️ 模型返回空响应，正在重试 ({attempt}/{max_retries})...")

                if self._stop_requested:
                    return StepResult(
                        success=False,
                        finished=True,
                        action=None,
                        thinking="",
                        message="Task stopped by user",
                    )

                response = self.model_client.request(self._context)

                # Print token usage if available
                if response.total_tokens > 0:
                    print(f"[TOKENS]{response.input_tokens},{response.output_tokens},{response.total_tokens}[/TOKENS]")

                # 检查响应是否为空
                if response.action and response.action.strip():
                    break  # 响应非空，退出重试循环
                elif attempt < max_retries:
                    print(f"⚠️ 模型返回空响应")
                    continue  # 继续重试

            except Exception as e:
                if self.agent_config.verbose:
                    traceback.print_exc()
                return StepResult(
                    success=False,
                    finished=True,
                    action=None,
                    thinking="",
                    message=f"Model error: {e}",
                )

        # Parse action from response
        try:
            action = parse_action(response.action)
        except ValueError:
            if self.agent_config.verbose:
                traceback.print_exc()
            # If action is empty, provide meaningful error message
            error_msg = response.action if response.action.strip() else "模型返回了空的动作，可能是推理被截断"
            action = finish(message=error_msg)

        if self.agent_config.verbose:
            # Print thinking process (cleaned up for readability)
            import re
            
            # Remove XML tags and clean up formatting
            thinking = response.thinking
            # Remove all XML-like tags (including <think>, </think>, <answer>, </answer>, etc.)
            thinking = re.sub(r'<[^>]+>', '', thinking)
            # Clean up multiple newlines
            thinking = re.sub(r'\n\s*\n', '\n', thinking)
            # Strip leading/trailing whitespace
            thinking = thinking.strip()
            
            if thinking:
                print(f"💭 思考过程:\n{thinking}\n")
            
            # Print action (simplified JSON)
            print(f"🎯 执行动作:")
            # Simplify JSON output
            simple_action = action.copy()
            if "_metadata" in simple_action:
                del simple_action["_metadata"]
            
            # Format as single line summary
            action_type = simple_action.pop("action", "Unknown")
            params = []
            for k, v in simple_action.items():
                params.append(f'{k}={json.dumps(v, ensure_ascii=False)}')
            
            summary = f"{action_type}({', '.join(params)})"
            # Pretty print simplified JSON
            print(json.dumps({
                "_metadata": action.get("_metadata", ""),
                "action": action_type,
                "summary": summary
            }, ensure_ascii=False, indent=2))
            print("")

        # Check for stop request before executing action
        if self._stop_requested:
            print("\n⏹️ Task stopped by user (before execution)")
            return StepResult(
                success=False,
                finished=True,
                action=action,
                thinking=response.thinking,
                message="Task stopped by user",
            )

        # Remove image from context to save space
        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])

        # Get actual device screen resolution for coordinate conversion
        # NOTE: screenshot.width/height may be compressed (e.g. 864x1920) 
        # but we need real device resolution (e.g. 1080x2400) for accurate tap coordinates
        from phone_agent.adb.unlock import get_screen_size
        device_width, device_height = get_screen_size(self.agent_config.device_id)
        logger.info(f"Using device resolution {device_width}x{device_height} for coordinate conversion (screenshot is {screenshot.width}x{screenshot.height})")

        # Execute action
        try:
            result = self.action_handler.execute(
                action, device_width, device_height
            )
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            result = self.action_handler.execute(
                finish(message=str(e)), device_width, device_height
            )

        # Add assistant response to context
        self._context.append(
            MessageBuilder.create_assistant_message(
                f"<think>{response.thinking}</think><answer>{response.action}</answer>"
            )
        )

        # Clean up old images to reduce token usage (keep recent 3 rounds)
        # This preserves conversation continuity while saving tokens
        self._cleanup_old_images(keep_recent=3)

        # If action failed (e.g., blocked by rules), add feedback to context
        # This tells the model what happened so it can try a different approach
        if not result.success and result.message:
            feedback_msg = f"[系统反馈] 上一个动作执行失败: {result.message}。请尝试其他方法来完成任务。"
            self._context.append(
                {"role": "user", "content": feedback_msg}
            )
            if self.agent_config.verbose:
                print(f"⚠️ {feedback_msg}\n")

        # Track action history for loop detection
        action_name = action.get("action", "unknown")
        action_key = f"{action_name}"
        # For Tap, include approximate position to detect position-specific loops
        if action_name == "Tap" and action.get("element"):
            elem = action.get("element", [0, 0])
            # Round to nearest 50 to group similar taps
            action_key = f"Tap({elem[0]//50*50},{elem[1]//50*50})"
        
        self._action_history.append(action_key)
        if len(self._action_history) > self._max_action_history:
            self._action_history.pop(0)
        
        # Detect action loops (same pattern repeated 3+ times)
        loop_detected = False
        if len(self._action_history) >= 6:
            # Check for 2-action loops (A-B-A-B-A-B)
            pattern_2 = self._action_history[-2:]
            if (self._action_history[-4:-2] == pattern_2 and 
                self._action_history[-6:-4] == pattern_2):
                loop_detected = True
        
        # Also check for single-action loops (A-A-A-A)
        if len(self._action_history) >= 4 and not loop_detected:
            if (self._action_history[-1] == self._action_history[-2] == 
                self._action_history[-3] == self._action_history[-4]):
                loop_detected = True
        
        if loop_detected:
            self._loop_detected_count += 1
            pattern_str = ' -> '.join(self._action_history[-2:]) if len(set(self._action_history[-2:])) > 1 else self._action_history[-1]
            
            if self._loop_detected_count >= self._max_loops_before_terminate:
                # Force terminate the task
                loop_msg = f"[系统反馈] 多次检测到重复动作循环: {pattern_str}。任务无法继续，请检查任务是否可行。"
                if self.agent_config.verbose:
                    print(f"❌ {loop_msg}\n")
                return StepResult(
                    success=False,
                    finished=True,
                    action=action,
                    thinking=response.thinking,
                    message=f"任务终止: 检测到无效操作循环 ({pattern_str})，无法完成任务",
                )
            else:
                loop_msg = f"[系统反馈] 检测到重复动作循环: {pattern_str}。这个操作序列没有效果，请尝试完全不同的方法来完成任务，或者报告任务无法完成。"
                self._context.append(
                    {"role": "user", "content": loop_msg}
                )
                if self.agent_config.verbose:
                    print(f"🔄 {loop_msg}\n")
            # Clear history to allow fresh start
            self._action_history.clear()
        else:
            # Reset loop counter if no loop detected after some actions
            if len(self._action_history) >= 4:
                self._loop_detected_count = 0

        # Check if finished
        finished = action.get("_metadata") == "finish" or result.should_finish

        if finished and self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            print(f"🎉 ✅ {msgs['task_completed']}: {result.message or action.get('message', msgs['done'])}\n")

        return StepResult(
            success=result.success,
            finished=finished,
            action=action,
            thinking=response.thinking,
            message=result.message or action.get("message"),
        )

    def _cleanup_old_images(self, keep_recent: int = 3) -> None:
        """
        Remove images from old context messages to reduce token usage.
        
        This method preserves conversation continuity by keeping all text content
        while removing image data from older messages. The model can still understand
        the full conversation history through text, but token usage is significantly reduced.
        
        Args:
            keep_recent: Number of recent user messages to keep images for (default: 3).
                        Recent images are needed for the model to understand current screen state.
        
        Example:
            After cleanup with keep_recent=3:
            - Message 1-7: Images removed, text preserved
            - Message 8-10: Full images kept
            
        Token savings:
            - ~250 tokens per old image removed
            - For a 10-step task: saves ~1750 tokens (7 old images × 250)
            - For a 20-step task: saves ~4250 tokens (17 old images × 250)
        """
        if len(self._context) <= 1:  # Only system message or empty
            return
        
        # Find all user message indices (skip system message at index 0)
        user_message_indices = []
        for i, msg in enumerate(self._context):
            if i == 0:  # Skip system message
                continue
            if msg.get('role') == 'user':
                user_message_indices.append(i)
        
        # If we have fewer user messages than keep_recent, no cleanup needed
        if len(user_message_indices) <= keep_recent:
            return
        
        # Calculate how many old messages to clean
        messages_to_clean = user_message_indices[:-keep_recent]
        
        # Remove images from old user messages
        cleaned_count = 0
        for idx in messages_to_clean:
            original_msg = self._context[idx]
            # Check if this message actually has images
            if isinstance(original_msg.get('content'), list):
                has_image = any(item.get('type') == 'image_url' for item in original_msg['content'])
                if has_image:
                    self._context[idx] = MessageBuilder.remove_images_from_message(self._context[idx])
                    cleaned_count += 1
        
        if cleaned_count > 0 and self.agent_config.verbose:
            print(f"🧹 清理了 {cleaned_count} 张历史截图，保留最近 {keep_recent} 轮")

    def generate_task_summary(self, task_name: str) -> str:
        """
        Generate a concise summary of the task execution using AI.
        
        This method analyzes the execution history and generates a 2-3 sentence
        summary suitable for email reports, highlighting the main objective,
        key actions, and final outcome.
        
        Args:
            task_name: Name of the task that was executed.
            
        Returns:
            A concise summary in Chinese (2-3 sentences), or a default message
            if generation fails.
            
        Example:
            >>> agent = PhoneAgent()
            >>> agent.run("打开微信并发送消息")
            >>> summary = agent.generate_task_summary("打开微信并发送消息")
            >>> print(summary)
            "成功打开微信应用，找到目标联系人并发送了指定消息。整个过程顺利完成，未出现任何错误。"
        """
        # Need at least some execution history
        if len(self._context) <= 2:
            return "任务已执行，但缺少详细执行记录。"
        
        # Extract execution steps from conversation context
        steps = []
        step_num = 1
        
        for msg in self._context[1:]:  # Skip system message
            if msg.get('role') == 'assistant':
                content = msg.get('content', '')
                # Extract thinking and action from XML tags
                import re
                
                # Try to extract thinking
                think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
                thinking = think_match.group(1).strip() if think_match else ""
                
                # Try to extract action
                answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
                action = answer_match.group(1).strip() if answer_match else ""
                
                # Build step description
                if thinking or action:
                    step_desc = f"步骤{step_num}: "
                    if thinking:
                        # Take first sentence or 80 chars
                        first_sentence = thinking.split('。')[0][:80]
                        step_desc += first_sentence
                    if action and len(action) < 100:
                        step_desc += f" -> {action[:50]}"
                    
                    steps.append(step_desc)
                    step_num += 1
        
        # Limit to recent steps to avoid token overflow
        recent_steps = steps[-10:] if len(steps) > 10 else steps
        history_text = "\n".join(recent_steps) if recent_steps else "执行了多个操作步骤"
        
        # Build summary prompt
        prompt = f"""请用2-3句话简洁地总结以下任务的执行过程（中文）。

任务要求：
- 说明任务的主要目标
- 概括执行了哪些关键操作
- 说明最终结果（成功完成/遇到问题等）

任务名称: {task_name}
执行步骤:
{history_text}

请提供一个专业、简洁的任务总结（2-3句话）:"""
        
        # Call model for summary generation
        try:
            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的任务执行助手，负责为自动化任务生成简洁清晰的执行总结。总结应该专业、准确、易于理解。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            # Use model client to generate summary
            response = self.model_client.request(messages)
            
            # Extract summary from response
            summary_text = ""
            if response.action and response.action.strip():
                summary_text = response.action
            elif response.thinking and response.thinking.strip():
                summary_text = response.thinking
            
            # Clean up XML tags if present
            import re
            summary_text = re.sub(r'<[^>]+>', '', summary_text).strip()
            
            # Validate summary is not empty and reasonable length
            if summary_text and len(summary_text) > 10:
                # Limit to reasonable length (max 500 chars)
                if len(summary_text) > 500:
                    summary_text = summary_text[:497] + "..."
                return summary_text
            else:
                return f"任务「{task_name}」执行完成，共执行{len(steps)}个步骤。"
                
        except Exception as e:
            # Fallback to simple summary
            if self.agent_config.verbose:
                print(f"⚠️ 生成任务总结失败: {e}")
            
            return f"任务「{task_name}」执行完成，共执行{len(steps)}个步骤。"

    @property
    def context(self) -> list[dict[str, Any]]:
        """Get the current conversation context."""
        return self._context.copy()

    @property
    def step_count(self) -> int:
        """Get the current step count."""
        return self._step_count


