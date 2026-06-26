# Accessibility Guide

Voice Jellyfin is designed from the ground up for users with motor disabilities who find standard TV remotes difficult or impossible to use.

---

## Navigation Mode

Navigation Mode is a focused state in which every voice command is interpreted as a TV remote key event.  When active:

- You do not need to prefix commands with a wake word
- Short, natural phrases like "down", "select", "back" are sent directly to the TV
- A pulsing indicator on the Lovelace card shows the mode is active

### Activating Navigation Mode

**Via voice (HA assist / voice satellite):**
Say the configured wake phrase (default: `"navigation mode"`).  The AI will detect the intent and activate the mode.

**Via the Lovelace card:**
Toggle the **Navigation Mode** switch on the `voice-jellyfin-card`.

**Via a physical button:**
Configure an accessibility button entity in Step 6 of the setup flow.  Any HA entity whose state changes to `on`, `press`, or `pressed` will activate Navigation Mode.

**Via a service call:**
```yaml
service: voice_jellyfin.navigation_mode_on
```

### Available Navigation Commands

Once Navigation Mode is active, say any of the following:

| Spoken phrase | Action |
|---------------|--------|
| up / move up / go up | D-pad UP |
| down / move down / go down | D-pad DOWN |
| left / go left | D-pad LEFT |
| right / go right | D-pad RIGHT |
| select / ok / okay / enter / confirm | D-pad CENTER (OK) |
| back / go back / return | BACK |
| home / go home / main menu | HOME |
| play / start | MEDIA PLAY |
| pause | MEDIA PAUSE |
| stop | MEDIA STOP |
| fast forward / forward | MEDIA FAST FORWARD |
| rewind / skip back | MEDIA REWIND |
| page up / previous page | PAGE UP |
| page down / next page | PAGE DOWN |
| volume up / louder | VOLUME UP |
| volume down / quieter / softer | VOLUME DOWN |
| mute / silence / unmute | MUTE |
| again / one more / repeat | Repeat last key |
| too far / go back one / undo | Reverse last key |

### Deactivating Navigation Mode

- Say **"stop navigation"** or **"exit navigation mode"**
- Toggle the Lovelace switch off
- Wait for the inactivity timeout (configurable; 30s / 60s / 120s / never)
- Call the `voice_jellyfin.navigation_mode_off` service

---

## Physical Accessibility Button Setup

A physical button (connected to HA via ZHA, Z-Wave, ESPHome, Shelly, etc.) gives single-press access to Navigation Mode.

### Example: Shelly Button

1. Pair the button with HA so it appears as a `binary_sensor` or `input_button`.
2. In the Voice Jellyfin options (or during config flow Step 6), set:
   - **Trigger Entity**: `binary_sensor.shelly_button_1`
   - **Trigger Type**: `State Change`
3. When the button is pressed, Navigation Mode activates automatically.

### Example: Input Button (virtual)

For testing or scripted triggers:
```yaml
input_button:
  accessibility_btn:
    name: "Activate Nav Mode"
    icon: mdi:wheelchair-accessibility
```

Set **Trigger Entity** to `input_button.accessibility_btn`.

---

## Timeout Tuning

The inactivity timeout controls how long Navigation Mode stays active without a command.

| Setting | Best for |
|---------|----------|
| **30 seconds** | Short sessions; prevents accidental mode lock |
| **60 seconds** | Default; balanced for most users |
| **120 seconds** | Users who speak slowly or need long pauses |
| **Never** | Always-on navigation for severe motor disability |

Adjust in **Settings → Devices & Services → Voice Jellyfin → Configure**.

---

## Tips for Low-Mobility Users

- **Combine with a voice satellite** (e.g. Wyoming Satellite, ESP32-S3-BOX) near the bed or couch for zero-touch activation.
- **Set timeout to "Never"** if the user only controls the TV by voice.
- **Use the Lovelace card** on a tablet mounted near the user for visual confirmation of the current mode.
- **Map a large accessibility switch** (sip-and-puff, head switch) to an HA `input_button` entity as the trigger.
