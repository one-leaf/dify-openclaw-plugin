"""
OpenClaw LLM implementation.

Extends OAICompatLargeLanguageModel to add custom header support
for OpenClaw Gateway routing.
"""

import logging
from typing import Optional, Union, Generator
import re
import uuid

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.config.logger_format import plugin_logger_handler
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    AssistantPromptMessage,
    UserPromptMessage,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(plugin_logger_handler)


class OpenclawLargeLanguageModel(OAICompatLargeLanguageModel):
    """
    OpenClaw LLM implementation.

    Extends OAICompatLargeLanguageModel to inject custom headers:
    - x-openclaw-agent-id: From model name (format: openclaw/{agent_id})
    - x-openclaw-session-key: Session routing
    """

    UUID_PATTERN = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )

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

        # Build custom headers
        extra_headers = {
            "x-openclaw-agent-id": agent_id,
        }

        # Extract session key from messages (SYSTEM block containing UUID)
        session_key, prompt_messages = self._extract_session_key_from_messages(prompt_messages)

        # Build session key header from message-extracted value
        if not session_key:
            if user:
                if self.UUID_PATTERN.match(user):
                    session_key = user
                else:
                    session_key = str(uuid.uuid5(uuid.NAMESPACE_DNS, user))
            else:
                session_key = str(uuid.uuid4())
            
        if ":" in session_key:
            # Pre-formatted value (contains colon), use as-is
            extra_headers["x-openclaw-session-key"] = session_key
        else:
            # Bare value, format as agent:{agent_id}:{uuid}
            extra_headers["x-openclaw-session-key"] = f"agent:{agent_id}:{session_key}"

        logger.info(
            "invoke: user=%s, agent_id=%s, session_key=%s,  messages_len=%d",
            user, agent_id, session_key, len(prompt_messages),
        )

        # Get endpoint URL and handle /v1 suffix
        endpoint_url = credentials.get("endpoint_url", "").rstrip("/")
        if endpoint_url.endswith("/v1"):
            endpoint_url = endpoint_url[:-3]
        if not endpoint_url:
            from dify_plugin.errors.model import InvokeBadRequestError
            raise InvokeBadRequestError("endpoint_url credential is required")

        # Store in credentials for parent class to use
        credentials["extra_headers"] = extra_headers
        credentials["endpoint_url"] = endpoint_url + "/v1"
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

    def _extract_session_key_from_messages(
        self, messages: list[PromptMessage]
    ) -> tuple[Optional[str], list[PromptMessage]]:
        """
        Extract session key from SYSTEM messages containing a bare UUID.

        Removes the UUID SYSTEM message block from the message list and
        returns it as the session key. All other messages are preserved.

        Returns:
            (session_key or None, cleaned_messages)
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
        if not endpoint_url:
            from dify_plugin.errors.model import InvokeBadRequestError
            raise InvokeBadRequestError("endpoint_url credential is required")

        # Store in credentials for parent class to use
        credentials["extra_headers"] = extra_headers
        credentials["endpoint_url"] = endpoint_url + "/v1"

        # Add required fields for OAICompat validation
        credentials["mode"] = "chat"

        # Call parent implementation
        super().validate_credentials(model, credentials)
