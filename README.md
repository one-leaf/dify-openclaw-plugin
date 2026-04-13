# OpenClaw Provider for Dify

A Dify models plugin that provides OpenAI-compatible API access with custom header support for the OpenClaw backend.

## Features

- **OpenAI-Compatible Protocol**: Works with Dify's standard OpenAI provider interface
- **Custom Header Support**: Adds OpenClaw Gateway routing headers:
  - `x-openclaw-agent-id`: Extracted from model name for agent selection
  - `x-openclaw-session-key`: Extracted from conversation for session routing

## Session Key Mechanism

The plugin automatically extracts the session key from the `SYSTEM` message block in the conversation:

1. **UUID detection**: If a SYSTEM block contains a bare UUID string, it is used as the session key
2. **Selective removal**: Only the UUID SYSTEM block is removed; other SYSTEM messages are preserved
3. **Fallback**: If no UUID session key is found, a random UUID is generated

### Usage in Dify

In your Dify application, configure a pre-prompt or variable that injects `{{sys.conversation_id}}` as a SYSTEM message. The plugin will detect and extract the UUID, then route the session accordingly.

## Installation

Copy the `models/openclaw` directory to your Dify installation:

```bash
cp -r models/openclaw /path/to/dify/api/core/model_runtime/model_providers/
```

## API Reference

OpenClaw Gateway API Documentation: https://docs.openclaw.ai/gateway/openai-http-api

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Chat completion (streaming supported) |
| `/v1/models` | GET | List available models |
| `/v1/models/{id}` | GET | Get model details |
| `/v1/embeddings` | POST | Embeddings |
| `/v1/responses` | POST | Responses API |

### Endpoint URL

```
POST http://<gateway-host>:<port>/v1/chat/completions
```

### Authentication

OpenClaw Gateway supports multiple auth modes:

| Auth Mode | Config | Header |
|-----------|--------|--------|
| Token | `gateway.auth.mode="token"` | `Authorization: Bearer <token>` |
| Password | `gateway.auth.mode="password"` | `Authorization: Bearer <password>` |
| Trusted Proxy | `gateway.auth.mode="trusted-proxy"` | - |
| None | `gateway.auth.mode="none"` | - |

### OpenClaw Headers

| Header | Required | Description |
|--------|----------|-------------|
| `x-openclaw-agent-id` | Yes | Extracted from model name (`openclaw/{agentId}`) |
| `x-openclaw-session-key` | Yes | Extracted from SYSTEM message or random UUID |

### Model Syntax

The following model specification formats are supported:

```yaml
model: "openclaw"           # Use default agent
model: "openclaw/default"   # Use default agent
model: "openclaw/<agentId>" # Use specific agent
model: "agent:<agentId>"    # Compatibility syntax
```

## Configuration

### Provider Credentials

| Field | Required | Description |
|-------|----------|-------------|
| `endpoint_url` | Yes | OpenClaw Gateway URL (e.g., `http://localhost:8080`) |
| `api_key` | No | API key or password for authentication (depends on auth mode) |
| `mode` | Yes | Completion type, set to `chat` |

### Model Configuration

After installing the provider, configure it in Dify's model management:

1. Navigate to Settings → Model Providers
2. Find "OpenClaw" in the provider list
3. Add credentials and configure routing options

## Usage

Once configured, select the OpenClaw provider when setting up LLM models in Dify applications.

## Development

### Project Structure

```
openclaw/
├── manifest.yaml          # Plugin metadata
├── main.py                # Entry point
├── requirements.txt       # Dependencies
├── _assets/
│   └── icon.svg           # Plugin icon
├── provider/
│   ├── openclaw.py        # OpenclawModelProvider
│   └── openclaw.yaml      # Provider config with credential schemas
└── models/
    └── llm/
        └── llm.py         # OpenclawLargeLanguageModel
```

### Testing

Test credentials validation through Dify's model management UI, or run:

```bash
cd /path/to/dify/api
python -c "from core.model_runtime.model_providers.openclaw import OpenClawProvider; p = OpenClawProvider(); p.validate_credentials('your-model', {'base_url': '...', 'api_key': '...'})"
```

## License

Same as Dify's main license.
