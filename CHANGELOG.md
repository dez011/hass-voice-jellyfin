# Changelog

## [0.4.0] — 2026-08-23

- Report when a Jellyfin client cannot be remote controlled instead of falsely reporting success; fix release version drift between manifest and const


## [0.3.9] — 2026-08-23

- Broadcast nav/playback commands to all sessions; fix button delivery when configured device has no active session


## [0.3.8] — 2026-08-23

- Surface remote control support in Active Session sensor; add Sessions sensor showing all user sessions; fix was Plezy not supporting Jellyfin remote control


## [0.3.7] — 2026-08-23

- Fix buttons doing nothing: device filter now soft-preference (falls back when configured device has no sessions)
- add system-session stripping so HA internal Hass sessions are never targeted


## [0.3.6] — 2026-08-23

- Add diagnostic WARNING log on every command so session-not-found failures show in HA logs


## [0.3.5] — 2026-08-22

- Fix buttons doing nothing: nav keys now use Jellyfin general command API (no ADB needed)
- pause/stop warn in logs when no session found


## [0.3.4] — 2026-08-22

- Add Active User sensor (configured Jellyfin username)
- add Active Session sensor (device + client app for that user)


## [0.3.3] — 2026-08-22

- Add Up/Down/Left/Right/Select d-pad navigation buttons to dashboard entities


## [0.3.2] — 2026-08-22

- Add dashboard button entities (Pause
- Resume
- Stop
- Next/Previous Episode
- Back
- Open Jellyfin)
- add Command text entity for typing any query
- fix VERSION const mismatch


## [0.3.1] — 2026-08-22

- Fix Test Commands screen ignoring picked preset when Submit is left on the default Search action
- Fix general commands (play/pause/next/stop) always targeting the first Jellyfin session instead of the configured default user

