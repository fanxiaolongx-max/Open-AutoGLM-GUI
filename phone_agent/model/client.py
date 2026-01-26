"""Model client for AI inference supporting multiple protocols."""

import json
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    anthropic = None

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    genai = None

from phone_agent.config.i18n import get_message


class ContextTooLargeError(Exception):
    """Raised when the context/request is too large for the API."""
    
    def __init__(self, original_error: Exception = None):
        self.original_error = original_error
        message = "上下文过长，请求体积超出 API 限制。建议：1) 减少对话历史长度；2) 使用新会话重新开始任务。"
        super().__init__(message)


@dataclass
class ModelConfig:
    """Configuration for the AI model."""

    base_url: str = "http://localhost:8000/v1"
    api_key: str = "EMPTY"
    model_name: str = "autoglm-phone-9b"
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2
    extra_body: dict[str, Any] = field(default_factory=dict)
    lang: str = "cn"  # Language for UI messages: 'cn' or 'en'
    protocol: str = "openai"  # Protocol type: 'openai', 'anthropic', 'gemini'


@dataclass
class ModelResponse:
    """Response from the AI model."""

    thinking: str
    action: str
    raw_content: str
    # Performance metrics
    time_to_first_token: float | None = None  # Time to first token (seconds)
    time_to_thinking_end: float | None = None  # Time to thinking end (seconds)
    total_time: float | None = None  # Total inference time (seconds)
    # Token usage
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ModelClient:
    """
    Client for interacting with AI models supporting multiple protocols.

    Supported protocols:
    - openai: OpenAI-compatible API
    - anthropic: Anthropic Claude API
    - gemini: Google Gemini API

    Args:
        config: Model configuration.
    """

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig()
        self._init_client()

    def _init_client(self):
        """Initialize the appropriate client based on protocol."""
        protocol = self.config.protocol.lower()

        if protocol == "anthropic":
            if not HAS_ANTHROPIC:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
            # Parse base_url for Anthropic - SDK adds /v1/messages automatically
            base_url = self.config.base_url.rstrip('/')
            if base_url.endswith('/v1/messages'):
                base_url = base_url[:-12]  # Remove /v1/messages
            elif base_url.endswith('/messages'):
                base_url = base_url[:-9]  # Remove /messages
            elif base_url.endswith('/v1'):
                base_url = base_url[:-3]  # Remove /v1
            self.client = anthropic.Anthropic(
                api_key=self.config.api_key or "EMPTY",
                base_url=base_url,
            )
        elif protocol == "gemini":
            if not HAS_GEMINI:
                raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")
            # Check if using a proxy/custom endpoint
            base_url = self.config.base_url.rstrip('/') if self.config.base_url else ""
            # Remove /v1 suffix if present
            if base_url.endswith('/v1'):
                base_url = base_url[:-3]
            is_official = not base_url or "googleapis.com" in base_url or "generativelanguage.googleapis.com" in base_url

            if is_official:
                # Official Gemini API
                genai.configure(api_key=self.config.api_key)
            else:
                # Proxy endpoint - need to set client_options
                genai.configure(
                    api_key=self.config.api_key,
                    transport='rest',
                    client_options={'api_endpoint': base_url}
                )
            self.client = genai.GenerativeModel(self.config.model_name)
        else:
            # Default to OpenAI protocol
            self.client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)

    def request(self, messages: list[dict[str, Any]]) -> ModelResponse:
        """
        Send a request to the model.

        Args:
            messages: List of message dictionaries in OpenAI format.

        Returns:
            ModelResponse containing thinking and action.

        Raises:
            ValueError: If the response cannot be parsed.
        """
        protocol = self.config.protocol.lower()

        if protocol == "anthropic":
            return self._request_anthropic(messages)
        elif protocol == "gemini":
            return self._request_gemini(messages)
        else:
            return self._request_openai(messages)

    def _request_openai(self, messages: list[dict[str, Any]]) -> ModelResponse:
        """Send request using OpenAI protocol with retry logic."""
        from openai import APIStatusError, APIConnectionError, APITimeoutError
        
        start_time = time.time()
        time_to_first_token = None
        time_to_thinking_end = None
        input_tokens = 0
        output_tokens = 0

        raw_content = ""
        buffer = ""
        action_markers = ["finish(message=", "do(action="]
        in_action_phase = False
        first_token_received = False
        
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"\n⚠️ API 请求失败，正在重试 ({attempt + 1}/{max_retries})...")
                    time.sleep(1)  # Brief pause before retry
                
                stream = self.client.chat.completions.create(
                    messages=messages,
                    model=self.config.model_name,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    top_p=self.config.top_p,
                    frequency_penalty=self.config.frequency_penalty,
                    extra_body=self.config.extra_body,
                    stream=True,
                    stream_options={"include_usage": True},
                )

                # Reset for each attempt
                raw_content = ""
                buffer = ""
                in_action_phase = False
                first_token_received = False

                for chunk in stream:
                    # Capture usage from final chunk
                    if hasattr(chunk, 'usage') and chunk.usage:
                        input_tokens = chunk.usage.prompt_tokens or 0
                        output_tokens = chunk.usage.completion_tokens or 0
                    if len(chunk.choices) == 0:
                        continue
                    if chunk.choices[0].delta.content is not None:
                        content = chunk.choices[0].delta.content
                        raw_content += content

                        if not first_token_received:
                            time_to_first_token = time.time() - start_time
                            first_token_received = True

                        if in_action_phase:
                            continue

                        buffer += content

                        marker_found = False
                        for marker in action_markers:
                            if marker in buffer:
                                thinking_part = buffer.split(marker, 1)[0]
                                print(thinking_part, end="", flush=True)
                                print()
                                in_action_phase = True
                                marker_found = True

                                if time_to_thinking_end is None:
                                    time_to_thinking_end = time.time() - start_time
                                break

                        if marker_found:
                            continue

                        is_potential_marker = False
                        for marker in action_markers:
                            for i in range(1, len(marker)):
                                if buffer.endswith(marker[:i]):
                                    is_potential_marker = True
                                    break
                            if is_potential_marker:
                                break

                        if not is_potential_marker:
                            print(buffer, end="", flush=True)
                            buffer = ""

                # Success - break out of retry loop
                break
                
            except APIStatusError as e:
                last_error = e
                error_msg = str(e)
                if "length limit" in error_msg.lower() or "too large" in error_msg.lower():
                    print(f"\n❌ 请求体积过大 (尝试 {attempt + 1}/{max_retries})")
                    if attempt == max_retries - 1:
                        raise ContextTooLargeError(original_error=e)
                else:
                    print(f"\n❌ API 错误 (尝试 {attempt + 1}/{max_retries}): {error_msg[:100]}")
                    if attempt == max_retries - 1:
                        raise
                continue
                
            except (APIConnectionError, APITimeoutError) as e:
                last_error = e
                print(f"\n❌ API 连接错误 (尝试 {attempt + 1}/{max_retries}): {type(e).__name__}")
                if attempt == max_retries - 1:
                    raise
                continue

        total_time = time.time() - start_time
        thinking, action = self._parse_response(raw_content)
        self._print_metrics(time_to_first_token, time_to_thinking_end, total_time, input_tokens, output_tokens)

        return ModelResponse(
            thinking=thinking,
            action=action,
            raw_content=raw_content,
            time_to_first_token=time_to_first_token,
            time_to_thinking_end=time_to_thinking_end,
            total_time=total_time,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    def _request_anthropic(self, messages: list[dict[str, Any]]) -> ModelResponse:
        """Send request using Anthropic protocol with retry logic."""
        start_time = time.time()
        time_to_first_token = None
        time_to_thinking_end = None
        input_tokens = 0
        output_tokens = 0

        # Convert OpenAI format messages to Anthropic format
        system_content = ""
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                if isinstance(content, str):
                    system_content = content
                continue

            # Convert content format
            if isinstance(content, list):
                # Handle multi-modal content
                converted_content = []
                for item in content:
                    if item.get("type") == "text":
                        converted_content.append({"type": "text", "text": item.get("text", "")})
                    elif item.get("type") == "image_url":
                        image_url = item.get("image_url", {}).get("url", "")
                        if image_url.startswith("data:image/"):
                            # Extract base64 data
                            parts = image_url.split(",", 1)
                            if len(parts) == 2:
                                media_type = parts[0].split(";")[0].replace("data:", "")
                                converted_content.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": parts[1],
                                    }
                                })
                content = converted_content
            else:
                content = [{"type": "text", "text": str(content)}]

            anthropic_messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content,
            })

        # Stream response with retry logic
        raw_content = ""
        buffer = ""
        action_markers = ["finish(message=", "do(action="]
        in_action_phase = False
        first_token_received = False
        
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"\n⚠️ API 请求失败，正在重试 ({attempt + 1}/{max_retries})...")
                    time.sleep(1)  # Brief pause before retry
                
                stream_context = self.client.messages.stream(
                    model=self.config.model_name,
                    max_tokens=self.config.max_tokens,
                    system=system_content if system_content else anthropic.NOT_GIVEN,
                    messages=anthropic_messages,
                    temperature=self.config.temperature,
                    top_p=self.config.top_p,
                )
                
                # Reset for each attempt
                raw_content = ""
                buffer = ""
                in_action_phase = False
                first_token_received = False

                with stream_context as stream:
                    for text in stream.text_stream:
                        raw_content += text

                        if not first_token_received:
                            time_to_first_token = time.time() - start_time
                            first_token_received = True

                        if in_action_phase:
                            continue

                        buffer += text

                        marker_found = False
                        for marker in action_markers:
                            if marker in buffer:
                                thinking_part = buffer.split(marker, 1)[0]
                                print(thinking_part, end="", flush=True)
                                print()
                                in_action_phase = True
                                marker_found = True

                                if time_to_thinking_end is None:
                                    time_to_thinking_end = time.time() - start_time
                                break

                        if marker_found:
                            continue

                        is_potential_marker = False
                        for marker in action_markers:
                            for i in range(1, len(marker)):
                                if buffer.endswith(marker[:i]):
                                    is_potential_marker = True
                                    break
                            if is_potential_marker:
                                break

                        if not is_potential_marker:
                            print(buffer, end="", flush=True)
                            buffer = ""

                    # Get final message for usage stats
                    final_message = stream.get_final_message()
                    if final_message and final_message.usage:
                        input_tokens = final_message.usage.input_tokens or 0
                        output_tokens = final_message.usage.output_tokens or 0
                
                # Success - break out of retry loop
                break
                
            except anthropic.RequestTooLargeError as e:
                last_error = e
                print(f"\n❌ 请求体积过大 (尝试 {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    # All retries exhausted, raise user-friendly error
                    raise ContextTooLargeError(original_error=e)
                # Continue to next retry
                continue
                
            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
                last_error = e
                print(f"\n❌ API 连接错误 (尝试 {attempt + 1}/{max_retries}): {type(e).__name__}")
                if attempt == max_retries - 1:
                    raise  # Re-raise the last error
                continue

        total_time = time.time() - start_time
        thinking, action = self._parse_response(raw_content)
        self._print_metrics(time_to_first_token, time_to_thinking_end, total_time, input_tokens, output_tokens)

        return ModelResponse(
            thinking=thinking,
            action=action,
            raw_content=raw_content,
            time_to_first_token=time_to_first_token,
            time_to_thinking_end=time_to_thinking_end,
            total_time=total_time,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    def _request_gemini(self, messages: list[dict[str, Any]]) -> ModelResponse:
        """Send request using Gemini protocol."""
        start_time = time.time()
        input_tokens = 0
        output_tokens = 0

        # Convert messages to Gemini format
        gemini_contents = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                # Gemini handles system as user instruction
                if isinstance(content, str):
                    gemini_contents.append({"role": "user", "parts": [content]})
                continue

            parts = []
            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif item.get("type") == "image_url":
                        image_url = item.get("image_url", {}).get("url", "")
                        if image_url.startswith("data:image/"):
                            import base64
                            data_parts = image_url.split(",", 1)
                            if len(data_parts) == 2:
                                image_data = base64.b64decode(data_parts[1])
                                parts.append({"mime_type": "image/png", "data": image_data})
            else:
                parts.append(str(content))

            gemini_role = "user" if role == "user" else "model"
            gemini_contents.append({"role": gemini_role, "parts": parts})

        # Generate response (Gemini doesn't support streaming in the same way)
        response = self.client.generate_content(
            gemini_contents,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
            ),
        )

        total_time = time.time() - start_time
        raw_content = response.text if response.text else ""

        # Get token usage from Gemini response
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0

        # Print content
        print(raw_content)

        thinking, action = self._parse_response(raw_content)
        self._print_metrics(None, None, total_time, input_tokens, output_tokens)

        return ModelResponse(
            thinking=thinking,
            action=action,
            raw_content=raw_content,
            time_to_first_token=None,
            time_to_thinking_end=None,
            total_time=total_time,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    def _print_metrics(self, time_to_first_token, time_to_thinking_end, total_time, input_tokens=0, output_tokens=0):
        """Print performance metrics."""
        lang = self.config.lang
        print()
        print("=" * 50)
        print(f"⏱️  {get_message('performance_metrics', lang)}:")
        print("-" * 50)
        if time_to_first_token is not None:
            print(f"{get_message('time_to_first_token', lang)}: {time_to_first_token:.3f}s")
        if time_to_thinking_end is not None:
            print(f"{get_message('time_to_thinking_end', lang)}:        {time_to_thinking_end:.3f}s")
        print(f"{get_message('total_inference_time', lang)}:          {total_time:.3f}s")
        if input_tokens > 0 or output_tokens > 0:
            print(f"📊 Tokens: {input_tokens} in + {output_tokens} out = {input_tokens + output_tokens} total")
        print("=" * 50)

    def _parse_response(self, content: str) -> tuple[str, str]:
        """
        Parse the model response into thinking and action parts.

        Parsing rules:
        1. If content contains 'finish(message=', everything before is thinking,
           everything from 'finish(message=' onwards is action.
        2. If rule 1 doesn't apply but content contains 'do(action=',
           everything before is thinking, everything from 'do(action=' onwards is action.
        3. Fallback: If content contains '<answer>', use legacy parsing with XML tags.
        4. Otherwise, return empty thinking and full content as action.

        Args:
            content: Raw response content.

        Returns:
            Tuple of (thinking, action).
        """
        # Rule 1: Check for finish(message=
        if "finish(message=" in content:
            parts = content.split("finish(message=", 1)
            thinking = parts[0].strip()
            action = "finish(message=" + parts[1]
            return thinking, action

        # Rule 2: Check for do(action=
        if "do(action=" in content:
            parts = content.split("do(action=", 1)
            thinking = parts[0].strip()
            action = "do(action=" + parts[1]
            return thinking, action

        # Rule 3: Fallback to legacy XML tag parsing
        if "<answer>" in content:
            parts = content.split("<answer>", 1)
            thinking = parts[0].replace("<think>", "").replace("</think>", "").strip()
            action = parts[1].replace("</answer>", "").strip()
            return thinking, action

        # Rule 4: No markers found, return content as action
        return "", content


class MessageBuilder:
    """Helper class for building conversation messages."""

    @staticmethod
    def create_system_message(content: str) -> dict[str, Any]:
        """Create a system message."""
        return {"role": "system", "content": content}

    @staticmethod
    def create_user_message(
        text: str, image_base64: str | None = None
    ) -> dict[str, Any]:
        """
        Create a user message with optional image.

        Args:
            text: Text content.
            image_base64: Optional base64-encoded image.

        Returns:
            Message dictionary.
        """
        content = []

        if image_base64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                }
            )

        content.append({"type": "text", "text": text})

        return {"role": "user", "content": content}

    @staticmethod
    def create_assistant_message(content: str) -> dict[str, Any]:
        """Create an assistant message."""
        return {"role": "assistant", "content": content}

    @staticmethod
    def remove_images_from_message(message: dict[str, Any]) -> dict[str, Any]:
        """
        Remove image content from a message to save context space.

        Args:
            message: Message dictionary.

        Returns:
            Message with images removed.
        """
        if isinstance(message.get("content"), list):
            message["content"] = [
                item for item in message["content"] if item.get("type") == "text"
            ]
        return message

    @staticmethod
    def build_screen_info(current_app: str, **extra_info) -> str:
        """
        Build screen info string for the model.

        Args:
            current_app: Current app name.
            **extra_info: Additional info to include.

        Returns:
            JSON string with screen info.
        """
        info = {"current_app": current_app, **extra_info}
        return json.dumps(info, ensure_ascii=False)
