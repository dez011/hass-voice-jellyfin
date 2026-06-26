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
 *   nav_switch: switch.voice_jellyfin_navigation_mode
 */

class VoiceJellyfinCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._commandHistory = [];
    this._maxHistory = 5;
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

    const status = this._stateVal(this._config.status_entity) || "Unknown";
    const provider = this._stateVal(this._config.provider_entity) || "None";
    const device = this._stateVal(this._config.device_entity) || "None";
    const lastMedia = this._stateVal(this._config.media_entity) || "—";
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
    `;

    this.shadowRoot.innerHTML = `
      <style>${styles}</style>
      <ha-card>
        <div class="header">
          <div style="display:flex;align-items:center;gap:8px;">
            <div class="status-dot" title="${status}"></div>
            <span class="title">${this._config.title}</span>
          </div>
          <div class="nav-badge">
            <span>Nav Mode</span>
          </div>
        </div>

        <div class="section">
          <div class="row">
            <span class="label">Status</span>
            <span class="value">${status}</span>
          </div>
          <div class="row">
            <span class="label">AI Provider</span>
            <span class="value" title="${provider}">${provider}</span>
          </div>
          <div class="row">
            <span class="label">Device</span>
            <span class="value" title="${device}">${device}</span>
          </div>
          <div class="row">
            <span class="label">Now Playing</span>
            <span class="value" title="${lastMedia}">${lastMedia}</span>
          </div>
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
