# Voice Jellyfin

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/release/dez011/hacs-voice-jellyfin.svg)](https://github.com/dez011/hacs-voice-jellyfin/releases)

Accessibility-focused voice control for [Jellyfin](https://jellyfin.org/) via Home Assistant.  
Say natural language commands to search, play, resume, and navigate your media — or activate **Navigation Mode** to control an Android TV by voice like a remote.

---

## Features

- **Natural Language Playback** — "Play the latest Breaking Bad episode", "Find something funny", "Resume what I was watching"
- **Navigation Mode** — Hands-free D-pad control: "up", "down", "select", "back", etc.
- **Physical Accessibility Button** — Assign any HA entity to activate Navigation Mode with a single press
- **Multiple AI Backends** — Ollama (local/private), OpenAI, Anthropic, Google Gemini, OpenRouter, or HA Conversation
- **Android TV / ADB Control** — Send key events, launch apps, deep-link to specific Jellyfin items
- **13 HA Services** — Automate from scripts, blueprints, or voice satellites
- **Custom Lovelace Card** — Live status dashboard with command history
- **Conversation Context** — The AI remembers up to 10 turns for follow-up commands

---

## Quick Install

### Via HACS

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/dez011/hacs-voice-jellyfin` as an **Integration**
3. Search **Voice Jellyfin** → Download → Restart HA
4. Settings → Devices & Services → Add Integration → **Voice Jellyfin**

### Manual

1. Download the latest ZIP from [Releases](https://github.com/dez011/hacs-voice-jellyfin/releases)
2. Copy `custom_components/voice_jellyfin/` into your HA `config/custom_components/`
3. Restart HA and add the integration

Full instructions: [docs/installation.md](docs/installation.md)

---

## Configuration Flow

The setup wizard guides you through 6 steps — no YAML needed:

| Step | What you configure |
|------|--------------------|
| 1. Network Mode | How HA reaches Jellyfin (local / HTTPS / Tailscale) |
| 2. Jellyfin | Server URL, API key, default user |
| 3. Android TV | Media player entity, ADB host/port |
| 4. AI Provider | Ollama, OpenAI, Anthropic, Gemini, OpenRouter, HA Conversation, or custom |
| 5. Navigation Mode | Wake phrase, inactivity timeout, TTS confirmation |
| 6. Accessibility Button | Optional physical trigger entity |

Full walkthrough: [docs/configuration.md](docs/configuration.md)

---

## Services

All services are available under the `voice_jellyfin` domain:

| Service | Description | Key fields |
|---------|-------------|------------|
| `voice_jellyfin.play` | Search and play media | `query`, `library_id` |
| `voice_jellyfin.search` | Search and return results | `query` |
| `voice_jellyfin.resume` | Resume in-progress media | `user_id` |
| `voice_jellyfin.pause` | Pause current session | `session_id` |
| `voice_jellyfin.stop` | Stop current session | `session_id` |
| `voice_jellyfin.navigate` | Send D-pad key | `direction` |
| `voice_jellyfin.scroll` | Scroll up/down N steps | `direction`, `amount` |
| `voice_jellyfin.select` | Press OK/Select | — |
| `voice_jellyfin.navigation_mode_on` | Activate Navigation Mode | — |
| `voice_jellyfin.navigation_mode_off` | Deactivate Navigation Mode | — |
| `voice_jellyfin.repeat_last_action` | Repeat previous key | — |
| `voice_jellyfin.go_home` | Press Home | — |
| `voice_jellyfin.go_back` | Press Back | — |

---

## Entities Created

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.voice_jellyfin_status` | Sensor | Connected / Navigating / Disconnected |
| `sensor.voice_jellyfin_ai_provider` | Sensor | Active AI provider name |
| `sensor.voice_jellyfin_current_device` | Sensor | Linked TV entity ID |
| `sensor.voice_jellyfin_last_command` | Sensor | Most recent voice command |
| `sensor.voice_jellyfin_last_media` | Sensor | Most recently played title |
| `switch.voice_jellyfin_navigation_mode` | Switch | Toggle Navigation Mode |
| `select.voice_jellyfin_ai_provider` | Select | Switch AI provider at runtime |

---

## Accessibility

Voice Jellyfin is designed for users with limited mobility:

- **Navigation Mode** eliminates the need for a physical remote
- **Physical button support** — any HA entity (ZHA, Z-Wave, ESPHome) can trigger Navigation Mode
- **Repeat / reverse** — "again", "too far", "go back one" prevent frustrating overshoot
- **Configurable timeout** — set to "Never" for always-on navigation

Full accessibility guide: [docs/accessibility.md](docs/accessibility.md)

Example automations: [docs/examples/automations.yaml](docs/examples/automations.yaml)

---

## Lovelace Card

Add the custom card to any dashboard:

```yaml
type: custom:voice-jellyfin-card
title: Voice Jellyfin
```

Shows: navigation mode status indicator, AI provider, connected device, last 5 commands, and a live voice-activity indicator.

See [docs/installation.md](docs/installation.md) for the resource URL setup.

---

## Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Write tests for new behaviour
4. Run `pytest tests/ --asyncio-mode=auto`
5. Submit a pull request

Please open an issue before starting large features.

---

## License

MIT © 2024 Miguel Hernandez — see [LICENSE](LICENSE).
