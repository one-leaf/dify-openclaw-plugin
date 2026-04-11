# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Dify plugin implementing a custom LLM provider (`openclaw`) using the `dify_plugin` SDK with custom header support for agent/session routing.

Backend API: OpenClaw Gateway (https://docs.openclaw.ai/gateway/openai-http-api)

### Model Name Format

Model name MUST be in format: `openclaw/{agent_id}`

```
openclaw/dify    # ✓ Valid - agent_id = "dify"
openclaw/main    # ✓ Valid - agent_id = "main"
dify             # ✗ Invalid - missing "openclaw/" prefix
```

Agent ID is extracted from the model name. If the model name is not in the correct format, `InvokeBadRequestError` is raised.

## Commands

- Install dependencies: `uv pip install -r openclaw/requirements.txt`
- Run plugin locally: `bin/dify plugin run`
- Validate plugin: `bin/dify plugin validate`
- Package plugin: `bin/dify plugin package openclaw`

## Architecture

```
openclaw/
├── manifest.yaml          # Plugin metadata
├── main.py                # Entry point
├── requirements.txt       # Dependencies: dify_plugin, openai, httpx
├── _assets/
│   └── icon.svg           # Plugin icon (lobster)
├── provider/
│   ├── openclaw.py        # OpenclawModelProvider
│   └── openclaw.yaml      # Provider config with credential schemas
└── models/
    └── llm/
        └── llm.py         # OpenclawLargeLanguageModel
```

### Key Components

**OpenclawModelProvider** (`provider/openclaw.py`):
- Extends `ModelProvider` from dify_plugin
- `validate_provider_credentials()`: No-op, validation deferred to model level

**OpenclawLargeLanguageModel** (`models/llm/llm.py`):
- Extends `OAICompatLargeLanguageModel` from dify_plugin
- `_invoke()`: Extracts agent_id from model name, injects custom headers, cleans messages
- `_clean_messages()`: Merges consecutive same-role messages, ensures at least one user message exists
- `validate_credentials()`: Validates model credentials with custom headers

### Custom Headers

| Header | Source |
|--------|--------|
| `x-openclaw-agent-id` | Extracted from model name (`openclaw/{agent_id}` → `{agent_id}`) |
| `x-openclaw-session-key` | From `openclaw_session_key` credential |

### Session Key Format

- **Bare value** (no colon, e.g., UUID): Auto-formatted as `agent:{agent_id}:{uuid}`
- **Pre-formatted** (contains colon): Used as-is

### Dify Built-in Variables

| Variable | Resolves To | Usage |
|----------|-------------|-------|
| `{{sys.conversation_id}}` | Current conversation ID | Recommended for `openclaw_session_key` |
| `{{sys.user_id}}` | Current user ID | Auto-passed as `user` parameter to API |

### Recommended Configuration

```yaml
endpoint_url: "http://localhost:8080"
api_key: ""  # Optional, depends on auth mode
mode: "chat"
openclaw_session_key: "{{sys.conversation_id}}"
```

### OpenClaw Gateway Auth Modes

| Mode | Config | Header |
|------|--------|--------|
| Token | `gateway.auth.mode="token"` | `Authorization: Bearer <token>` |
| Password | `gateway.auth.mode="password"` | `Authorization: Bearer <password>` |
| Trusted Proxy | `gateway.auth.mode="trusted-proxy"` | None required |
| None | `gateway.auth.mode="none"` | None required |

For `api_key` credential in Dify:
- Use token/password for token/password auth modes
- Can be empty for trusted-proxy/none modes

### Message Cleaning

The `_clean_messages()` method handles API compatibility:

1. **Preserves** system and tool messages unchanged
2. **Merges** consecutive assistant messages (combines content and tool_calls)
3. **Filters** empty messages (no content and no tool calls)
4. **Appends** an empty user message if none exists (required by OpenAI-compatible API)
