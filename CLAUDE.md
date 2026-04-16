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
- `_extract_session_key_from_messages()`: Extracts UUID session key from SYSTEM messages
- Raises `InvokeBadRequestError` if `endpoint_url` credential is missing

### Custom Headers

| Header | Source |
|--------|--------|
| `x-openclaw-agent-id` | Extracted from model name (`openclaw/{agent_id}` → `{agent_id}`) |
| `x-openclaw-session-key` | Extracted from SYSTEM message block containing UUID, or random UUID fallback |

### Session Key Mechanism

The plugin extracts the session key from `SYSTEM` messages in the conversation:

1. **UUID detection**: Scans SYSTEM blocks for a bare UUID string
2. **Extraction**: If found, uses it as session key and removes **only that UUID block**
3. **Fallback**: Generates a random UUID if no SYSTEM UUID is found
4. **Format**: Bare UUID → `agent:{agent_id}:{uuid}`; pre-formatted (contains `:`) → used as-is

Non-UUID SYSTEM messages are preserved and forwarded to the API.

### Message Cleaning

The `_clean_messages()` method handles API compatibility:

1. **Preserves** system and tool messages unchanged
2. **Merges** consecutive assistant messages (combines content and tool_calls)
3. **Filters** empty messages (no content and no tool calls)
4. **Appends** an empty user message if none exists (required by OpenAI-compatible API)
