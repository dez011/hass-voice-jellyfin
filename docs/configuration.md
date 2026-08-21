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
| **Username** *(optional)* | Informational only — the next step lets you pick your real user from a list |

The integration tests connectivity immediately.  If it cannot reach the server you will see a "Cannot connect" error — check the URL and that Jellyfin is running.

One server URL can only be set up once — adding the same server a second time (e.g. by mistake) is blocked, since every service call fans out to *all* configured entries and a duplicate would fire every command twice.

*Screenshot placeholder: Jellyfin connection step*

---

## Step 2b — Which Jellyfin User?

Once connected, the wizard fetches your server's user list and asks which one this entry acts as — for resume, favorites, and watch history, which Jellyfin scopes per-user. Pick **Auto-detect** on a single-user server, or your own profile if the server has more than one account (e.g. you're setting up a second TV for your brother — pick *his* profile when configuring *his* TV).

*Screenshot placeholder: user picker*

---

## Step 3 — Android TV / Fire TV Device

| Field | Description |
|-------|-------------|
| **Media Player Entity** | Select the `media_player.*` entity for your TV (needs the `androidtv` integration set up first) |
| **ADB Host** *(optional)* | Direct ADB TCP host — used automatically if no Media Player Entity is selected, so Fire TV/Android TV control works even without the `androidtv` HA integration |
| **ADB Port** | Default `5555` |
| **Enable Wake-on-Command** | Wake the screen before sending key events |
| **Jellyfin App Package** | Android package "open Jellyfin" launches. Default `org.jellyfin.androidtv` (the official app). Using Astra, Findroid, or another client instead? Find its package name via `adb shell pm list packages \| grep -i jellyfin` (or the client's name) and paste it here. |
| **Jellyfin Device Name** *(optional)* | **Only needed with more than one TV/person on the same Jellyfin server.** Matches this TV's Jellyfin session by device name (Jellyfin Dashboard → Devices) or client app name (e.g. `Astra`). Leave blank on a single-TV setup — commands then just act on whichever session is active. See [Multiple TVs / Multiple Users](#multiple-tvs--multiple-users) below. |

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

- Jellyfin connection, and which Jellyfin user this entry acts as
- AI provider and settings
- TV device, ADB host, the Jellyfin app package, and the Jellyfin device name filter
- Navigation timeout, wake phrase, spoken confirmation, hot mic phrase
- Accessibility button entity
- Re-index the media catalog, or run a search/playback test against this entry's server and TV

Each entry's options are independent — reconfiguring one TV's device name filter or user doesn't touch any other entry.

---

## Multiple TVs / Multiple Users

Voice Jellyfin has no built-in concept of "rooms" — instead, **add the integration once per TV**. Each config entry is independent, with its own TV controller, its own Jellyfin user, and (once set) its own device name filter. Two entries pointed at the same Jellyfin server never conflict.

**Setup for a second TV (e.g. your brother's Fire TV with a different Jellyfin client):**

1. Settings → Devices & Services → **Add Integration** → Voice Jellyfin again
2. Same Jellyfin URL and API key as your first entry
3. On the user picker, choose *his* Jellyfin profile — not yours
4. Pick his Fire TV's `media_player` entity (or ADB host)
5. Set **Jellyfin App Package** if he's using a different client (Astra, Findroid, etc.) than the official app
6. Set **Jellyfin Device Name** to something that matches how his TV shows up in Jellyfin — check Jellyfin Dashboard → Devices for the exact device name, or ask "what's playing" once his TV is open in Jellyfin and read the `device`/`client` attributes off the **Now Playing** sensor

Once both entries have a device name set, commands sent through each entry's `voice_jellyfin.voice_command` (or its dedicated Assist automation) only ever touch its own TV's session — "pause" on your device never pauses his show, and vice versa. Without a device name set (the default, single-TV behavior), a command acts on whichever Jellyfin session happens to be active.

The **Now Playing** sensor (`sensor.voice_jellyfin_now_playing`, one per entry) shows the title, client app, device name, user, and paused state of what that entry currently sees — the fastest way to confirm a device name filter is matching the right session.
