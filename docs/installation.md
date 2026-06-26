# Installation

## Prerequisites

- Home Assistant 2024.1 or later
- HACS (Home Assistant Community Store) installed
- A running Jellyfin server accessible from HA
- (Optional) An Android TV / Fire TV with ADB enabled

---

## Install via HACS (Recommended)

1. Open Home Assistant and navigate to **HACS → Integrations**.
2. Click the three-dot menu (⋮) in the top-right corner and select **Custom repositories**.
3. In the **Repository** field enter:
   ```
   https://github.com/dez011/hacs-voice-jellyfin
   ```
4. Set **Category** to **Integration** and click **Add**.
5. Search for **Voice Jellyfin** in the HACS integrations list.
6. Click **Download** and confirm.
7. **Restart Home Assistant** (Settings → System → Restart).

---

## Manual Installation

1. Download the latest release ZIP from the [Releases page](https://github.com/dez011/hacs-voice-jellyfin/releases).
2. Extract the ZIP and locate the `custom_components/voice_jellyfin/` directory.
3. Copy the entire `voice_jellyfin/` folder into your HA configuration directory under `custom_components/`:
   ```
   config/
   └── custom_components/
       └── voice_jellyfin/   ← copy here
   ```
4. **Restart Home Assistant**.

---

## Add the Integration

After restarting:

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Voice Jellyfin** and click it.
3. Follow the multi-step configuration flow (see [Configuration](configuration.md)).

---

## Lovelace Card

To add the dashboard card, include the JS resource in your Lovelace configuration:

```yaml
# configuration.yaml or via UI (Settings → Dashboards → Resources)
lovelace:
  resources:
    - url: /local/voice-jellyfin-card.js
      type: module
```

Copy `custom_components/voice_jellyfin/lovelace/voice-jellyfin-card.js` to your
`config/www/` directory (rename to `voice-jellyfin-card.js`), then add the card to
a dashboard:

```yaml
type: custom:voice-jellyfin-card
title: Voice Jellyfin
status_entity: sensor.voice_jellyfin_status
provider_entity: sensor.voice_jellyfin_ai_provider
device_entity: sensor.voice_jellyfin_current_device
command_entity: sensor.voice_jellyfin_last_command
media_entity: sensor.voice_jellyfin_last_media
nav_switch: switch.voice_jellyfin_navigation_mode
```
