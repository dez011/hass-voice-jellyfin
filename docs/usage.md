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

### When there's more than one match

If a search is ambiguous the integration asks instead of guessing:

> *"play batman"* → **"I found 1: The Dark Knight (2008), 2: Batman
> Begins (2005). Which one?"**

Answer with an ordinal or the title:

- "the first one" / "number two" / "2"
- "batman begins"

Saying anything else drops the question and is handled normally.

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

## 6. Troubleshooting

| Symptom | Check |
|---------|-------|
| Keys don't reach the TV | Is the `androidtv` integration set up, or an ADB host configured? Fire TV needs ADB debugging enabled (Settings → My Fire TV → Developer Options → ADB Debugging) |
| "No active player session found" | Open the Jellyfin app on the TV first — "open jellyfin" does this by voice |
| Voice does nothing | Confirm the bridge automation calls `voice_jellyfin.voice_command` and check Settings → Devices → Voice Jellyfin sensors |
| AI replies are odd | Turn AI off in Options — everything above still works rule-based |
