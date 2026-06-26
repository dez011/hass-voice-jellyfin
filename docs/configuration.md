# Configuration

Voice Jellyfin uses a guided multi-step configuration flow — no YAML editing required.

---

## Step 1 — Network Mode

Choose how your Jellyfin server and Home Assistant are connected:

| Option | Description |
|--------|-------------|
| **Local HTTP** | Same network, plain HTTP (e.g. `http://192.168.1.x:8096`) |
| **HTTPS / Reverse Proxy** | Nginx/Caddy terminating TLS |
| **Tailscale / MagicDNS** | Jellyfin reachable over Tailscale |
| **Custom** | Any URL you provide manually |

*Screenshot placeholder: network mode selection*

---

## Step 2 — Jellyfin Connection

| Field | Description |
|-------|-------------|
| **Jellyfin URL** | Full URL including port, e.g. `http://192.168.1.50:8096` |
| **API Key** | Generate one in Jellyfin → Dashboard → API Keys |
| **Username** *(optional)* | Used for username/password auth instead of API key |
| **Default User ID** *(optional)* | Used for resume/favorites calls |

The integration tests connectivity immediately.  If it cannot reach the server you will see a "Cannot connect" error — check the URL and that Jellyfin is running.

*Screenshot placeholder: Jellyfin connection step*

---

## Step 3 — Android TV / Fire TV Device

| Field | Description |
|-------|-------------|
| **Media Player Entity** | Select the `media_player.*` entity for your TV |
| **ADB Host** *(optional)* | Direct ADB TCP host if you need raw ADB commands |
| **ADB Port** | Default `5555` |
| **Enable Wake-on-Command** | Wake the screen before sending key events |

Leave all fields blank to skip TV control (voice commands will only affect Jellyfin playback).

*Screenshot placeholder: Android TV step*

---

## Step 4 — AI Provider

Choose your preferred AI backend:

| Provider | Notes |
|----------|-------|
| **Home Assistant Conversation** | Free, uses whatever conversation agent is configured in HA |
| **Ollama (Local)** | Recommended for privacy; runs on your LAN |
| **OpenAI** | Requires API key; GPT-4o-mini is cost-effective |
| **Anthropic (Claude)** | Requires API key |
| **Google Gemini** | Requires API key |
| **OpenRouter** | Multi-model gateway; API key required |
| **OpenAI-Compatible** | LM Studio, vLLM, or any OpenAI-compatible server |

### Ollama sub-step

| Field | Default | Description |
|-------|---------|-------------|
| Host | `localhost` | Ollama server hostname |
| Port | `11434` | Ollama server port |
| Use HTTPS | off | Enable if Ollama is behind a TLS proxy |
| Model | `llama3` | Model tag (e.g. `mistral`, `phi3`) |
| Context Size | `4096` | Tokens in context window |
| Keep Alive | `5m` | How long to keep the model loaded |
| Enable Streaming | on | Stream tokens for lower perceived latency |
| Timeout | `15` | Seconds before giving up |

*Screenshot placeholder: Ollama configuration*

---

## Step 5 — Navigation Mode

| Field | Default | Description |
|-------|---------|-------------|
| **Wake Phrase** | `navigation mode` | Words in a voice command that activate nav mode |
| **Inactivity Timeout** | `60s` | Seconds of silence before nav mode auto-deactivates |
| **Continuous Listening** | on | Stay in nav mode after each command |
| **Speak Confirmation** | on | TTS feedback when nav mode activates/deactivates |

*Screenshot placeholder: Navigation mode settings*

---

## Step 6 — Accessibility Button (Optional)

Assign any HA entity as a physical trigger for Navigation Mode:

| Field | Description |
|-------|-------------|
| **Trigger Entity** | Any entity (button, input_boolean, binary_sensor) |
| **Trigger Type** | `State Change` (on/off) or `HA Event` |

This enables users with motor disabilities to activate Navigation Mode with a single button press.

*Screenshot placeholder: Accessibility button step*

---

## Options Flow (Reconfigure)

After initial setup, go to **Settings → Devices & Services → Voice Jellyfin → Configure** to adjust:

- Navigation timeout
- Wake phrase
- Spoken confirmation
- Accessibility button entity
