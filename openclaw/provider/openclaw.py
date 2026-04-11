"""
OpenClaw Model Provider.

OpenClaw Gateway provider with custom routing headers.
"""

import logging
from collections.abc import Mapping

from dify_plugin import ModelProvider

logger = logging.getLogger(__name__)


class OpenclawModelProvider(ModelProvider):
    """
    OpenClaw Model Provider.

    Provides OpenAI-compatible API access with additional headers
    for OpenClaw Gateway routing:
    - x-openclaw-agent-id: Agent selection (from model name)
    - x-openclaw-session-key: Session routing
    """

    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """
        Validate provider credentials.

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        # Validation is handled by model instance during first invocation
        pass
