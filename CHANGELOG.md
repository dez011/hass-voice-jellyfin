# Changelog

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

