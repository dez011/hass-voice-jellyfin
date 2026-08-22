# Using Voice Jellyfin

This guide covers day-to-day use once the integration is set up
(see [installation.md](installation.md) and [configuration.md](configuration.md)).

The goal: **say a keyword once, then talk to the TV naturally** — no more
"Alexa, up… Alexa, up… Alexa, up" twenty times to move four spots.

---

## 1. Wire your voice source to the pipeline

All spoken text enters through one service: `voice_jellyfin.voice_command`.
Point whatever produces speech-to-text at it — Home Assistant Assist, a
voice satellite, or an Alexa/Google routine that forwards text.

### Home Assistant Assist (sentence trigger)

```yaml
automation:
  - alias: "Voice Jellyfin bridge"
    triggers:
      - trigger: conversation
        command: "jellyfin {request}"
    actions:
      - action: voice_jellyfin.voice_command
        data:
          text: "{{ trigger.slots.request }}"
        response_variable: reply
      - set_conversation_response: "{{ reply.speech }}"
```

Now "jellyfin play the dark knight", "jellyfin navigation mode", etc. all
work through Assist. For a hands-free experience use a wake-word satellite
(e.g. an ESP32-S3 box or the Voice Preview Edition) so nothing needs
pressing at all.

### Voice satellite (Assist pipeline)

Attach the same automation to your satellite's pipeline, or call
`voice_command` from an `assist_satellite` automation. The `reply.speech`
response can be piped into any `tts.speak` action.

---

## 2. Navigation Mode — the accessibility remote

Say the wake phrase (default **"navigation mode"**, configurable in the
wizard) and the integration switches into remote-control mode. Every
utterance is now a key press — no wake word needed per command:

```
"navigation mode"      → Navigation mode on.
"down"                 → D-pad down
"right five times"     → five D-pad rights
"up 3"                 → three D-pad ups
"down down down"       → three D-pad downs
"select"               → OK
"again"                → repeat the last key
"too far"              → reverse the last key (overshoot recovery)
"volume up two times"  → volume +2
"exit navigation mode" → Navigation mode off.
```

Counts work with digits ("right 5") or words ("right five times", "twice"),
capped at 20. The full phrase list is in
[accessibility.md](accessibility.md).

Navigation Mode can also be toggled by the Lovelace card switch, the
`navigation_mode_on`/`off` services, or a physical accessibility button
configured in the wizard. It auto-exits after the configured timeout
(set it to "Never" for an always-on remote).

Anything that isn't a key phrase — "play breaking bad" — falls through to
the media pipeline, so you don't have to leave Navigation Mode to start
a show.

---

## 3. Media commands

Outside (or inside) Navigation Mode, natural commands control Jellyfin:

```
"open jellyfin"                       → launches the app on the TV
"play the dark knight"                → searches and plays
"play season 3 of breaking bad"      → plays S3E1 (or resumes mid-episode)
"play the latest episode of bluey"   → newest episode
"search for something funny"          → lists matches
"resume" / "pause" / "stop"
"next episode" / "skip intro"
"lower the quality"                   → steps the bitrate down (buffering fix)
"what's playing?"
```

"open jellyfin" launches the package set as **Jellyfin App Package** in the
TV device options (default: the official `org.jellyfin.androidtv` app). If
you're using an alternate client like Astra or Findroid, set that in
Options → TV Device or "open jellyfin" will try to launch an app that isn't
installed.

### When there's more than one match

If a search is ambiguous the integration asks instead of guessing:

> *"play batman"* → **"I found 1: The Dark Knight (2008), 2: Batman
> Begins (2005). Which one?"**

Answer with an ordinal or the title:

- "the first one" / "number two" / "2"
- "batman begins"

Saying anything else drops the question and is handled normally.

---

## 3b. More than one TV / more than one person

Voice Jellyfin doesn't assume you're the only one watching. If you set a
**Jellyfin Device Name** for a TV during setup (Options → TV Device), every
command from that entry — play, pause, stop, resume, quality, favorites —
only ever targets sessions matching that device or client app name. Two
Fire TVs, two people, no cross-talk: pausing from your entry never pauses
your brother's show.

Without a device name set (the default), a command acts on whichever
Jellyfin session is currently active — fine for a single-TV household.

Check `sensor.voice_jellyfin_now_playing` (one per config entry) to see
exactly what that entry currently sees: title, client app, device, user,
and paused state. If it's showing the wrong show, your device name filter
probably doesn't match Jellyfin's actual device/client name — check
Jellyfin Dashboard → Devices for the exact string. See
[configuration.md](configuration.md#multiple-tvs--multiple-users) for the
full multi-TV setup walkthrough.

When a targeted TV has no matching Jellyfin session (e.g. its app isn't
open), you'll hear "Jellyfin isn't open on `<device name>`" instead of a
command silently landing on the wrong TV.

---

## 4. Hot mic (continuous listening)

Say the hot-mic phrase (default **"hey jellyfin"**) to toggle continuous
mode: every utterance is routed as a command and unknown speech is
silently ignored — useful with a satellite configured to re-open the mic
on the `voice_jellyfin_hot_mic_ready` event. Say the phrase again to stop
listening.

---

## 5. The AI toggle

AI parsing is optional and lives behind **Options → AI Provider →
"Enable AI"**:

- **Off** — a fast rule-based parser handles all the commands above. No
  network calls, no AI required.
- **On** — free-form phrasing ("put on that show about the chemistry
  teacher") goes to your configured provider (Ollama locally, or
  OpenAI/Anthropic/Gemini/OpenRouter/HA Conversation).

**If the AI backend is unreachable, nothing breaks**: the command falls
back to the same rule-based parser automatically, so navigation, playback,
volume, and search keep working while your Ollama box is down. You'll only
lose the fancy free-form phrasing until it's back.

---

## Testing without a microphone

You don't need to speak anything to try this out. The sensors this
integration creates are read-only — there are no buttons on them — so
commands are run from one of the three places below.

### Fastest: Developer Tools → Actions

Zero setup, works the moment the integration loads. Go to **Developer
Tools → Actions**, switch to YAML mode with the toggle on the right, and
paste:

```yaml
action: voice_jellyfin.voice_command
data:
  text: open jellyfin
```

Press **Perform action**. Because `voice_command` returns a response,
the spoken reply appears right below the button. Swap the text for
anything you'd say out loud:

```yaml
action: voice_jellyfin.voice_command
data:
  text: search for batman
```

Individual services work too, if you want to skip the language parsing:

```yaml
action: voice_jellyfin.navigate      # up/down/left/right/select/back/home
data:
  direction: down
```

```yaml
action: voice_jellyfin.play
data:
  query: the dark knight
```

### Options flow

**Settings → Devices & Services → Voice Jellyfin → Configure → Test
Commands**. Type free text or pick from the **Quick command** dropdown
(open jellyfin, pause, up/down/left/right, navigation mode, …), choose
**Test voice command**, and the reply is shown in the form. Handy when
you don't remember the exact phrasing.

### The dashboard card

Two places in the UI exercise the exact same pipeline real speech goes
through:

**The Lovelace card** (`type: custom:voice-jellyfin-card`) has a "Test
Controls" section:

- **D-pad + Back** — up/down/left/right/select and back buttons call
  `voice_jellyfin.navigate` directly, the same as Navigation Mode key
  presses
- **Open Jellyfin** — a one-tap way to confirm your **Jellyfin App
  Package** setting actually launches the client you installed (Astra,
  Findroid, the official app, etc.)
- **Text box + Send** — type anything you'd say out loud ("play the dark
  knight", "pause", "what's playing", "navigation mode") and it's routed
  through `voice_jellyfin.voice_command` — the same wake-phrase / nav-mode
  / AI-or-rule-based pipeline a real utterance takes. The spoken reply
  shows up right under the box.

Set `show_controls: false` in the card's YAML config to hide this section
on a dashboard you don't want cluttered.

**Options → Voice Command Tester** (Settings → Devices & Services → Voice
Jellyfin → Configure → Test) has the same "Test voice command" action —
type free text or pick a **Quick command** preset (open jellyfin, pause,
up/down/left/right, navigation mode, etc.) and it runs through the full
pipeline too. The original Search/Play actions are still there for
checking Jellyfin search results directly.

Both are handy for confirming a **Jellyfin Device Name** filter, an app
package, or a phrase works before wiring up an actual voice source.

---

## 6. Troubleshooting

| Symptom | Check |
|---------|-------|
| Keys don't reach the TV | Is the `androidtv` integration set up, or an ADB host configured? Fire TV needs ADB debugging enabled (Settings → My Fire TV → Developer Options → ADB Debugging) |
| "No active player session found" | Open the Jellyfin app on the TV first — "open jellyfin" does this by voice |
| "Jellyfin isn't open on `<name>`" | Your **Jellyfin Device Name** filter (Options → TV Device) doesn't match a currently active session. Check `sensor.voice_jellyfin_now_playing` on another entry for the real device/client name, or open Jellyfin on the TV first |
| Commands affect the wrong TV | Set a distinct **Jellyfin Device Name** on each entry — see [configuration.md](configuration.md#multiple-tvs--multiple-users) |
| "open jellyfin" opens the wrong (or no) app | Set **Jellyfin App Package** in Options → TV Device to match the client actually installed (Astra, Findroid, etc.) |
| Voice does nothing | Confirm the bridge automation calls `voice_jellyfin.voice_command` and check Settings → Devices → Voice Jellyfin sensors |
| Not sure what to say, or don't have a mic handy | Use the Lovelace card's Test Controls or Options → Voice Command Tester → Test voice command — see [Testing without a microphone](#testing-without-a-microphone) above |
| AI replies are odd | Turn AI off in Options — everything above still works rule-based |
