/**
 * voice-jellyfin-card — Custom Lovelace card for Voice Jellyfin
 *
 * Shows navigation mode status, AI provider, connected device, recent
 * commands, and a voice-activity indicator.
 *
 * Usage in dashboard YAML:
 *   type: custom:voice-jellyfin-card
 *   title: Voice Jellyfin          # optional
 *   status_entity: sensor.voice_jellyfin_status
 *   provider_entity: sensor.voice_jellyfin_ai_provider
 *   device_entity: sensor.voice_jellyfin_current_device
 *   command_entity: sensor.voice_jellyfin_last_command
 *   media_entity: sensor.voice_jellyfin_last_media
 *   now_playing_entity: sensor.voice_jellyfin_now_playing
 *   nav_switch: switch.voice_jellyfin_navigation_mode
 *   show_controls: true              # optional — set false to hide the test controls
 */

class VoiceJellyfinCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._commandHistory = [];
    this._maxHistory = 5;
    this._lastReply = "";
    this._sending = false;
  }

  // ---------------------------------------------------------------------------
  // Lovelace API
  // ---------------------------------------------------------------------------

  setConfig(config) {
    if (!config) throw new Error("voice-jellyfin-card: invalid configuration");
    this._config = {
      title: "Voice Jellyfin",
      status_entity: "sensor.voice_jellyfin_status",
      provider_entity: "sensor.voice_jellyfin_ai_provider",
      device_entity: "sensor.voice_jellyfin_current_device",
      command_entity: "sensor.voice_jellyfin_last_command",
      media_entity: "sensor.voice_jellyfin_last_media",
      now_playing_entity: "sensor.voice_jellyfin_now_playing",
      nav_switch: "switch.voice_jellyfin_navigation_mode",
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    const prev = this._hass;
    this._hass = hass;

    // Track command history
    const cmd = this._stateVal(this._config.command_entity);
    if (cmd && cmd !== "unavailable" && cmd !== "unknown") {
      const prevCmd = prev ? this._stateValFrom(prev, this._config.command_entity) : "";
      if (cmd !== prevCmd) {
        this._commandHistory.unshift(cmd);
        if (this._commandHistory.length > this._maxHistory) {
          this._commandHistory.pop();
        }
      }
    }

    this._render();
  }

  getCardSize() {
    return 4;
  }

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  _render() {
    if (!this._hass) return;

    // Preserve the free-text command box across re-renders — `hass` is
    // reassigned on every entity state change anywhere in HA, which would
    // otherwise wipe out whatever the user is mid-typing.
    const commandInputEl = this.shadowRoot.getElementById("command-input");
    const preservedInputValue = commandInputEl ? commandInputEl.value : "";
    const inputHadFocus = this.shadowRoot.activeElement === commandInputEl;

    const status = this._stateVal(this._config.status_entity) || "Unknown";
    const provider = this._stateVal(this._config.provider_entity) || "None";
    const device = this._stateVal(this._config.device_entity) || "None";
    const lastMedia = this._stateVal(this._config.media_entity) || "—";

    // Live now-playing state — shows WHICH client/device is actually
    // playing, not just the last thing a voice command started.
    const nowPlayingState = this._config.now_playing_entity
      ? this._hass.states[this._config.now_playing_entity]
      : null;
    const nowPlayingTitle =
      nowPlayingState && nowPlayingState.state && nowPlayingState.state !== "unavailable" && nowPlayingState.state !== "unknown"
        ? nowPlayingState.state
        : lastMedia;
    const npAttrs = (nowPlayingState && nowPlayingState.attributes) || {};
    const nowPlayingSubtitle = [npAttrs.client, npAttrs.device]
      .filter((v) => v && v !== "Unknown")
      .join(" · ");
    const navSwitch = this._config.nav_switch
      ? this._hass.states[this._config.nav_switch]
      : null;
    const navActive = navSwitch ? navSwitch.state === "on" : status === "Navigating";
    const connected = status === "Connected" || status === "Navigating";

    const styles = `
      :host {
        display: block;
        font-family: var(--paper-font-body1_-_font-family, sans-serif);
        font-size: 14px;
      }
      ha-card {
        padding: 16px;
        overflow: hidden;
      }
      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 14px;
      }
      .title {
        font-size: 16px;
        font-weight: 600;
        color: var(--primary-text-color);
      }
      .status-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: ${connected ? "var(--success-color, #4CAF50)" : "var(--error-color, #F44336)"};
        flex-shrink: 0;
        animation: ${navActive ? "pulse 1.4s infinite" : "none"};
      }
      @keyframes pulse {
        0% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.35); opacity: 0.6; }
        100% { transform: scale(1); opacity: 1; }
      }
      .nav-badge {
        display: ${navActive ? "inline-flex" : "none"};
        align-items: center;
        gap: 6px;
        background: var(--accent-color, #2196F3);
        color: white;
        border-radius: 12px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .section {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-bottom: 14px;
      }
      .row {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .label {
        color: var(--secondary-text-color);
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.4px;
      }
      .value {
        font-weight: 500;
        color: var(--primary-text-color);
        max-width: 55%;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        text-align: right;
      }
      .now-playing-subtitle {
        font-size: 11px;
        color: var(--secondary-text-color);
        max-width: 70%;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        text-align: right;
        margin-left: auto;
      }
      .divider {
        height: 1px;
        background: var(--divider-color, #e0e0e0);
        margin: 10px 0;
      }
      .history-title {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.4px;
        color: var(--secondary-text-color);
        margin-bottom: 6px;
      }
      .history-item {
        font-size: 13px;
        color: var(--primary-text-color);
        padding: 3px 0;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .history-item:last-child {
        border-bottom: none;
      }
      .history-empty {
        font-size: 12px;
        color: var(--disabled-text-color);
        font-style: italic;
      }
      .toggle-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-top: 12px;
      }
      .toggle-label {
        font-size: 13px;
        color: var(--primary-text-color);
      }
      ha-switch {
        --mdc-theme-secondary: var(--accent-color, #2196F3);
      }
      .voice-indicator {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-top: 4px;
        font-size: 12px;
        color: ${navActive ? "var(--accent-color, #2196F3)" : "var(--disabled-text-color)"};
      }
      .mic-icon {
        font-size: 16px;
      }
      .controls-section {
        margin-top: 4px;
      }
      .dpad {
        display: grid;
        grid-template-columns: repeat(3, 44px);
        grid-template-rows: repeat(3, 44px);
        gap: 4px;
        justify-content: center;
        margin: 8px 0 10px;
      }
      .ctrl-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        border: none;
        border-radius: 8px;
        background: var(--secondary-background-color, #eee);
        color: var(--primary-text-color);
        font-size: 15px;
        cursor: pointer;
        padding: 0;
        transition: background 0.15s ease;
      }
      .ctrl-btn:hover {
        background: var(--accent-color, #2196F3);
        color: white;
      }
      .ctrl-btn:active {
        transform: scale(0.94);
      }
      .ctrl-select {
        font-weight: 700;
        font-size: 12px;
        background: var(--accent-color, #2196F3);
        color: white;
      }
      .ctrl-row {
        display: flex;
        gap: 8px;
        margin-bottom: 10px;
      }
      .ctrl-wide {
        flex: 1;
        height: 38px;
        font-size: 13px;
        gap: 6px;
      }
      .command-row {
        display: flex;
        gap: 8px;
      }
      .command-row input {
        flex: 1;
        min-width: 0;
        padding: 8px 10px;
        border-radius: 8px;
        border: 1px solid var(--divider-color, #e0e0e0);
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        font-size: 13px;
      }
      .command-row .ctrl-btn {
        width: 64px;
        height: auto;
        font-size: 13px;
      }
      .command-reply {
        margin-top: 8px;
        font-size: 12px;
        color: var(--secondary-text-color);
        white-space: pre-wrap;
        word-break: break-word;
      }
    `;

    const esc = (v) => this._escapeHtml(v);

    this.shadowRoot.innerHTML = `
      <style>${styles}</style>
      <ha-card>
        <div class="header">
          <div style="display:flex;align-items:center;gap:8px;">
            <div class="status-dot" title="${esc(status)}"></div>
            <span class="title">${esc(this._config.title)}</span>
          </div>
          <div class="nav-badge">
            <span>Nav Mode</span>
          </div>
        </div>

        <div class="section">
          <div class="row">
            <span class="label">Status</span>
            <span class="value">${esc(status)}</span>
          </div>
          <div class="row">
            <span class="label">AI Provider</span>
            <span class="value" title="${esc(provider)}">${esc(provider)}</span>
          </div>
          <div class="row">
            <span class="label">Device</span>
            <span class="value" title="${esc(device)}">${esc(device)}</span>
          </div>
          <div class="row">
            <span class="label">Now Playing</span>
            <span class="value" title="${esc(nowPlayingTitle)}">${esc(nowPlayingTitle)}</span>
          </div>
          ${nowPlayingSubtitle ? `
          <div class="row">
            <span class="label"></span>
            <span class="now-playing-subtitle" title="${esc(nowPlayingSubtitle)}">${esc(nowPlayingSubtitle)}</span>
          </div>
          ` : ""}
        </div>

        <div class="divider"></div>

        <div>
          <div class="history-title">Recent Commands</div>
          ${
            this._commandHistory.length > 0
              ? this._commandHistory
                  .map(c => `<div class="history-item">${this._escapeHtml(c)}</div>`)
                  .join("")
              : '<span class="history-empty">No commands yet</span>'
          }
        </div>

        ${navSwitch ? `
        <div class="toggle-row">
          <span class="toggle-label">Navigation Mode</span>
          <ha-switch
            id="nav-toggle"
            ${navActive ? "checked" : ""}
          ></ha-switch>
        </div>
        ` : ""}

        <div class="voice-indicator">
          <span class="mic-icon">🎙</span>
          <span>${navActive ? "Listening for navigation commands…" : "Say a command to control Jellyfin"}</span>
        </div>

        ${this._config.show_controls === false ? "" : `
        <div class="divider"></div>

        <div class="controls-section">
          <div class="history-title">Test Controls</div>
          <div class="dpad">
            <div></div>
            <button class="ctrl-btn" data-dir="up" title="Up" aria-label="Up">▲</button>
            <div></div>
            <button class="ctrl-btn" data-dir="left" title="Left" aria-label="Left">◀</button>
            <button class="ctrl-btn ctrl-select" data-dir="select" title="Select" aria-label="Select">OK</button>
            <button class="ctrl-btn" data-dir="right" title="Right" aria-label="Right">▶</button>
            <div></div>
            <button class="ctrl-btn" data-dir="down" title="Down" aria-label="Down">▼</button>
            <div></div>
          </div>
          <div class="ctrl-row">
            <button class="ctrl-btn ctrl-wide" id="back-btn">⤺ Back</button>
            <button class="ctrl-btn ctrl-wide" id="open-jellyfin-btn">▶ Open Jellyfin</button>
          </div>
          <div class="command-row">
            <input
              type="text"
              id="command-input"
              placeholder="Type a command… e.g. play the dark knight"
              ${this._sending ? "disabled" : ""}
            />
            <button class="ctrl-btn" id="send-btn" ${this._sending ? "disabled" : ""}>
              ${this._sending ? "…" : "Send"}
            </button>
          </div>
          ${this._lastReply ? `<div class="command-reply">${esc(this._lastReply)}</div>` : ""}
        </div>
        `}
      </ha-card>
    `;

    // Wire up the switch toggle
    if (navSwitch) {
      const toggle = this.shadowRoot.getElementById("nav-toggle");
      if (toggle) {
        toggle.addEventListener("change", (e) => {
          const newState = e.target.checked ? "turn_on" : "turn_off";
          this._hass.callService("switch", newState, {
            entity_id: this._config.nav_switch,
          });
        });
      }
    }

    // Wire up the no-microphone test controls (D-pad, back, open jellyfin,
    // free-text command box) — lets the whole voice pipeline be exercised
    // from the dashboard without speaking a word.
    if (this._config.show_controls !== false) {
      this.shadowRoot.querySelectorAll(".dpad [data-dir]").forEach((btn) => {
        btn.addEventListener("click", () => this._callNavigate(btn.dataset.dir));
      });
      const backBtn = this.shadowRoot.getElementById("back-btn");
      if (backBtn) backBtn.addEventListener("click", () => this._callNavigate("back"));
      const openBtn = this.shadowRoot.getElementById("open-jellyfin-btn");
      if (openBtn) openBtn.addEventListener("click", () => this._sendCommand("open jellyfin"));

      const input = this.shadowRoot.getElementById("command-input");
      const sendBtn = this.shadowRoot.getElementById("send-btn");
      if (input) {
        input.value = preservedInputValue;
        if (inputHadFocus) {
          input.focus();
          input.setSelectionRange(preservedInputValue.length, preservedInputValue.length);
        }
        input.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            const text = input.value.trim();
            if (text) this._sendCommand(text);
          }
        });
      }
      if (sendBtn) {
        sendBtn.addEventListener("click", () => {
          const text = input ? input.value.trim() : "";
          if (text) this._sendCommand(text);
        });
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Test control actions
  // ---------------------------------------------------------------------------

  async _callNavigate(direction) {
    if (!this._hass || !direction) return;
    try {
      await this._hass.callService("voice_jellyfin", "navigate", { direction });
    } catch (err) {
      console.error("voice-jellyfin-card: navigate failed", err);
      this._lastReply = `Error: ${err.message || err}`;
      this._render();
    }
  }

  async _sendCommand(text) {
    if (!this._hass || !text) return;
    this._sending = true;
    this._render();

    try {
      // Prefer the WebSocket call so we can surface the spoken reply
      // (`voice_command` supports an optional response) directly in the card.
      const result = await this._hass.callWS({
        type: "call_service",
        domain: "voice_jellyfin",
        service: "voice_command",
        service_data: { text },
        return_response: true,
      });
      const speech = result && result.response && result.response.speech;
      this._lastReply = speech ? `🗣 "${text}" → ${speech}` : `Sent: "${text}"`;
    } catch (err) {
      try {
        await this._hass.callService("voice_jellyfin", "voice_command", { text });
        this._lastReply = `Sent: "${text}" (no reply text available)`;
      } catch (err2) {
        console.error("voice-jellyfin-card: voice_command failed", err2);
        this._lastReply = `Error: ${err2.message || err2}`;
      }
    }

    this._sending = false;
    this._render();
    const input = this.shadowRoot.getElementById("command-input");
    if (input) {
      input.value = "";
      input.focus();
    }
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  _stateVal(entityId) {
    if (!this._hass || !entityId) return null;
    const state = this._hass.states[entityId];
    return state ? state.state : null;
  }

  _stateValFrom(hass, entityId) {
    if (!hass || !entityId) return null;
    const state = hass.states[entityId];
    return state ? state.state : null;
  }

  _escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
}

customElements.define("voice-jellyfin-card", VoiceJellyfinCard);

// Register the card with the Lovelace card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: "voice-jellyfin-card",
  name: "Voice Jellyfin Card",
  description:
    "Shows navigation mode status, AI provider, connected device, and recent command history for the Voice Jellyfin integration.",
  preview: false,
  documentationURL:
    "https://github.com/dez011/hacs-voice-jellyfin/blob/main/docs/configuration.md",
});
