"""Constants for the Voice Jellyfin integration."""
from __future__ import annotations

DOMAIN = "voice_jellyfin"
VERSION = "0.1.0"

# Config entry keys
CONF_JELLYFIN_URL = "jellyfin_url"
CONF_JELLYFIN_API_KEY = "jellyfin_api_key"
CONF_JELLYFIN_USERNAME = "jellyfin_username"
CONF_JELLYFIN_PASSWORD = "jellyfin_password"
CONF_JELLYFIN_DEFAULT_USER = "jellyfin_default_user"
CONF_JELLYFIN_LIBRARIES = "jellyfin_libraries"

CONF_TV_TYPE = "tv_type"
CONF_ANDROID_TV_ENTITY = "android_tv_entity"
CONF_APPLE_TV_ENTITY = "apple_tv_entity"
CONF_ADB_HOST = "adb_host"
CONF_ADB_PORT = "adb_port"
CONF_TV_WAKE_SUPPORT = "tv_wake_support"

# TV types
TV_TYPE_NONE = "none"
TV_TYPE_ANDROID = "android_tv"
TV_TYPE_APPLE = "apple_tv"

CONF_AI_PROVIDER = "ai_provider"
CONF_AI_API_KEY = "ai_api_key"
CONF_AI_MODEL = "ai_model"
CONF_AI_BASE_URL = "ai_base_url"
CONF_AI_TEMPERATURE = "ai_temperature"
CONF_AI_MAX_TOKENS = "ai_max_tokens"
CONF_AI_STREAMING = "ai_streaming"
CONF_AI_TIMEOUT = "ai_timeout"
CONF_AI_ORG_ID = "ai_org_id"

CONF_OLLAMA_HOST = "ollama_host"
CONF_OLLAMA_PORT = "ollama_port"
CONF_OLLAMA_HTTPS = "ollama_https"
CONF_OLLAMA_MODEL = "ollama_model"
CONF_OLLAMA_CONTEXT_SIZE = "ollama_context_size"
CONF_OLLAMA_KEEP_ALIVE = "ollama_keep_alive"

CONF_NAV_WAKE_PHRASE = "nav_wake_phrase"
CONF_NAV_TIMEOUT = "nav_timeout"
CONF_NAV_CONTINUOUS = "nav_continuous"
CONF_NAV_CONFIRMATION_SPEECH = "nav_confirmation_speech"
CONF_NAV_SPEECH_VOLUME = "nav_speech_volume"

CONF_BUTTON_ENTITY = "button_entity"
CONF_BUTTON_TRIGGER = "button_trigger"
CONF_BUTTON_BEHAVIOR = "button_behavior"

CONF_NETWORK_MODE = "network_mode"

# AI Providers
AI_PROVIDER_HA_CONVERSATION = "ha_conversation"
AI_PROVIDER_OPENAI = "openai"
AI_PROVIDER_ANTHROPIC = "anthropic"
AI_PROVIDER_GEMINI = "gemini"
AI_PROVIDER_OPENROUTER = "openrouter"
AI_PROVIDER_OLLAMA = "ollama"
AI_PROVIDER_OPENAI_COMPAT = "openai_compat"

AI_PROVIDERS = [
    AI_PROVIDER_HA_CONVERSATION,
    AI_PROVIDER_OPENAI,
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_GEMINI,
    AI_PROVIDER_OPENROUTER,
    AI_PROVIDER_OLLAMA,
    AI_PROVIDER_OPENAI_COMPAT,
]

AI_PROVIDER_LABELS = {
    AI_PROVIDER_HA_CONVERSATION: "Home Assistant Conversation",
    AI_PROVIDER_OPENAI: "OpenAI",
    AI_PROVIDER_ANTHROPIC: "Anthropic (Claude)",
    AI_PROVIDER_GEMINI: "Google Gemini",
    AI_PROVIDER_OPENROUTER: "OpenRouter",
    AI_PROVIDER_OLLAMA: "Ollama (Local)",
    AI_PROVIDER_OPENAI_COMPAT: "OpenAI-Compatible (LM Studio / vLLM / Custom)",
}

# Navigation timeouts (seconds; 0 = never)
NAV_TIMEOUT_30 = 30
NAV_TIMEOUT_60 = 60
NAV_TIMEOUT_120 = 120
NAV_TIMEOUT_NEVER = 0

NAV_TIMEOUT_OPTIONS = {
    "30s": NAV_TIMEOUT_30,
    "60s": NAV_TIMEOUT_60,
    "120s": NAV_TIMEOUT_120,
    "Never": NAV_TIMEOUT_NEVER,
}

DEFAULT_NAV_WAKE_PHRASE = "navigation mode"
DEFAULT_NAV_TIMEOUT = NAV_TIMEOUT_60
DEFAULT_AI_TEMPERATURE = 0.3
DEFAULT_AI_MAX_TOKENS = 512
DEFAULT_AI_TIMEOUT = 15
DEFAULT_OLLAMA_HOST = "localhost"
DEFAULT_OLLAMA_PORT = 11434
DEFAULT_OLLAMA_CONTEXT_SIZE = 4096
DEFAULT_OLLAMA_KEEP_ALIVE = "5m"

# Network modes
NETWORK_MODE_LOCAL = "local"
NETWORK_MODE_HTTPS = "https"
NETWORK_MODE_TAILSCALE = "tailscale"
NETWORK_MODE_CADDY = "caddy"
NETWORK_MODE_CUSTOM = "custom"

# Services
SERVICE_PLAY = "play"
SERVICE_SEARCH = "search"
SERVICE_RESUME = "resume"
SERVICE_PAUSE = "pause"
SERVICE_STOP = "stop"
SERVICE_NAVIGATE = "navigate"
SERVICE_SCROLL = "scroll"
SERVICE_SELECT = "select"
SERVICE_NAVIGATION_MODE_ON = "navigation_mode_on"
SERVICE_NAVIGATION_MODE_OFF = "navigation_mode_off"
SERVICE_REPEAT_LAST_ACTION = "repeat_last_action"
SERVICE_GO_HOME = "go_home"
SERVICE_GO_BACK = "go_back"

# Remote key events
KEY_UP = "up"
KEY_DOWN = "down"
KEY_LEFT = "left"
KEY_RIGHT = "right"
KEY_SELECT = "select"
KEY_BACK = "back"
KEY_HOME = "home"
KEY_PLAY = "play"
KEY_PAUSE = "pause"
KEY_STOP = "stop"
KEY_FAST_FORWARD = "fast_forward"
KEY_REWIND = "rewind"
KEY_PAGE_UP = "page_up"
KEY_PAGE_DOWN = "page_down"
KEY_VOLUME_UP = "volume_up"
KEY_VOLUME_DOWN = "volume_down"
KEY_MUTE = "mute"

# HA event names
EVENT_NAVIGATION_MODE_CHANGED = f"{DOMAIN}_navigation_mode_changed"
EVENT_COMMAND_RECEIVED = f"{DOMAIN}_command_received"

# Coordinator update interval (seconds)
UPDATE_INTERVAL = 30

# Session memory size (turns)
AI_CONTEXT_MAX_TURNS = 10

# Logging
LOGGER_NAME = f"custom_components.{DOMAIN}"
