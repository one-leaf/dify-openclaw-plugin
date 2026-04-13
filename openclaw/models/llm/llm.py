"""
OpenClaw LLM implementation.

Extends OAICompatLargeLanguageModel to add custom header support
for OpenClaw Gateway routing.
"""

from typing import Optional, Union, Generator
import re
import uuid

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    AssistantPromptMessage,
    UserPromptMessage,
)


class OpenclawLargeLanguageModel(OAICompatLargeLanguageModel):
    """
    OpenClaw LLM implementation.

    Extends OAICompatLargeLanguageModel to inject custom headers:
    - x-openclaw-agent-id: From model name (format: openclaw/{agent_id})
    - x-openclaw-session-key: Session routing
    """

    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> Union[LLMResult, Generator]:
        """
        Invoke the OpenClaw backend with custom headers.

        Model name must be in format: openclaw/{agent_id}
        Agent ID is extracted from the model name.
        """
        # Extract agent_id from model name
        # Model name must be in format: openclaw/{agent_id}
        if not model.startswith("openclaw/"):
            from dify_plugin.errors.model import InvokeBadRequestError
            raise InvokeBadRequestError(
                f"Invalid model name format: {model}. "
                f"Expected format: openclaw/{{agent_id}} (e.g., openclaw/dify)"
            )

        agent_id = model[len("openclaw/"):]
        if not agent_id:
            from dify_plugin.errors.model import InvokeBadRequestError
            raise InvokeBadRequestError(
                f"Agent ID cannot be empty in model name: {model}. "
                f"Expected format: openclaw/{{agent_id}} (e.g., openclaw/dify)"
            )

        # Extract session key from messages (SYSTEM block containing UUID)
        session_key, prompt_messages = self._extract_session_key_from_messages(prompt_messages)

        # Build custom headers
        extra_headers = {
            "x-openclaw-agent-id": agent_id,
        }

        # Build session key header from message-extracted value
        if session_key:
            if ":" in session_key:
                # Pre-formatted value (contains colon), use as-is
                extra_headers["x-openclaw-session-key"] = session_key
            else:
                # Bare value, format as agent:{agent_id}:{uuid}
                extra_headers["x-openclaw-session-key"] = f"agent:{agent_id}:{session_key}"

        # Get endpoint URL and handle /v1 suffix
        endpoint_url = credentials.get("endpoint_url", "").rstrip("/")
        if endpoint_url.endswith("/v1"):
            endpoint_url = endpoint_url[:-3]

        # Store in credentials for parent class to use
        credentials["extra_headers"] = extra_headers
        credentials["endpoint_url"] = endpoint_url + "/v1" if endpoint_url else None
        credentials["mode"] = "chat"

        # Merge consecutive messages with the same role to follow API specs
        prompt_messages = self._clean_messages(prompt_messages)

        # Call parent implementation
        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
        )

    def _clean_messages(self, messages: list[PromptMessage]) -> list[PromptMessage]:
        """
        Merge consecutive messages with the same role.

        Tool and system messages are always preserved.
        Empty messages (no content and no tool calls) are filtered out.

        Ensures at least one user message exists for API compatibility.
        """
        cleaned: list[PromptMessage] = []
        has_user_message = False

        for m in messages:
            # Track if we have a user message
            if isinstance(m, UserPromptMessage):
                has_user_message = True

            # Tool and system messages should NEVER be filtered or merged
            if isinstance(m, (ToolPromptMessage, SystemPromptMessage)):
                cleaned.append(m.model_copy())
                continue

            # Filter out empty messages (no content and no tool calls)
            has_tool_calls = isinstance(m, AssistantPromptMessage) and m.tool_calls
            if not m.content and not has_tool_calls:
                continue

            if cleaned and cleaned[-1].role == m.role:
                prev = cleaned[-1]
                # Merge content if both are strings
                if isinstance(prev.content, str) and isinstance(m.content, str):
                    if prev.content and m.content:
                        prev.content += "\n\n" + m.content
                    else:
                        prev.content = prev.content or m.content

                # Merge tool_calls if both are assistants
                if isinstance(prev, AssistantPromptMessage) and isinstance(m, AssistantPromptMessage):
                    if m.tool_calls:
                        if not prev.tool_calls:
                            prev.tool_calls = []
                        prev.tool_calls.extend(m.tool_calls)
            else:
                cleaned.append(m.model_copy())

        # Ensure at least one user message exists for API compatibility
        if not has_user_message:
            # Add an empty user message at the end
            cleaned.append(UserPromptMessage(content=""))

        return cleaned

    UUID_PATTERN = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )

    def _extract_session_key_from_messages(
        self, messages: list[PromptMessage]
    ) -> tuple[str, list[PromptMessage]]:
        """
        Look for SYSTEM messages whose content is a bare UUID string.
        Only UUID SYSTEM messages are removed; all other messages are preserved.

        If no UUID session key is found, generate a random UUID as fallback.

        Returns:
            (session_key, cleaned_messages)
        """
        cleaned: list[PromptMessage] = []
        found_session_key: str | None = None

        for m in messages:
            if isinstance(m, SystemPromptMessage):
                content = m.content
                if isinstance(content, str) and self.UUID_PATTERN.match(content.strip()):
                    # Found UUID session key, extract and remove this block
                    found_session_key = content.strip()
                    continue
            cleaned.append(m.model_copy())

        if found_session_key is None:
            found_session_key = str(uuid.uuid4())

        return found_session_key, cleaned

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials with custom headers.

        Model name must be in format: openclaw/{agent_id}
        Agent ID is extracted from the model name.
        """
        # Extract agent_id from model name
        if not model.startswith("openclaw/"):
            from dify_plugin.errors.model import InvokeBadRequestError
            raise InvokeBadRequestError(
                f"Invalid model name format: {model}. "
                f"Expected format: openclaw/{{agent_id}} (e.g., openclaw/dify)"
            )

        agent_id = model[len("openclaw/"):]
        if not agent_id:
            from dify_plugin.errors.model import InvokeBadRequestError
            raise InvokeBadRequestError(
                f"Agent ID cannot be empty in model name: {model}. "
                f"Expected format: openclaw/{{agent_id}} (e.g., openclaw/dify)"
            )

        # Build custom headers
        extra_headers = {
            "x-openclaw-agent-id": agent_id,
        }

        # Session key: random UUID for validation
        extra_headers["x-openclaw-session-key"] = f"agent:{agent_id}:{uuid.uuid4()}"

        # Get endpoint URL and handle /v1 suffix
        endpoint_url = credentials.get("endpoint_url", "").rstrip("/")
        if endpoint_url.endswith("/v1"):
            endpoint_url = endpoint_url[:-3]

        # Store in credentials for parent class to use
        credentials["extra_headers"] = extra_headers
        credentials["endpoint_url"] = endpoint_url + "/v1" if endpoint_url else None

        # Add required fields for OAICompat validation
        credentials["mode"] = "chat"

        # Call parent implementation
        super().validate_credentials(model, credentials)
