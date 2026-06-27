"""Config flow for Voice Jellyfin — no YAML required."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    LOGGER_NAME,
    AI_PROVIDERS,
    AI_PROVIDER_LABELS,
    AI_PROVIDER_HA_CONVERSATION,
    AI_PROVIDER_OLLAMA,
    AI_PROVIDER_OPENAI_COMPAT,
    CONF_JELLYFIN_URL,
    CONF_JELLYFIN_API_KEY,
    CONF_JELLYFIN_USERNAME,
    CONF_JELLYFIN_DEFAULT_USER,
    CONF_TV_TYPE,
    CONF_ANDROID_TV_ENTITY,
    CONF_APPLE_TV_ENTITY,
    CONF_ADB_HOST,
    CONF_ADB_PORT,
    CONF_TV_WAKE_SUPPORT,
    TV_TYPE_NONE,
    TV_TYPE_ANDROID,
    TV_TYPE_APPLE,
    CONF_AI_PROVIDER,
    CONF_AI_API_KEY,
    CONF_AI_MODEL,
    CONF_AI_BASE_URL,
    CONF_AI_TEMPERATURE,
    CONF_AI_MAX_TOKENS,
    CONF_AI_STREAMING,
    CONF_AI_TIMEOUT,
    CONF_OLLAMA_HOST,
    CONF_OLLAMA_PORT,
    CONF_OLLAMA_HTTPS,
    CONF_OLLAMA_MODEL,
    CONF_OLLAMA_CONTEXT_SIZE,
    CONF_OLLAMA_KEEP_ALIVE,
    CONF_NAV_WAKE_PHRASE,
    CONF_NAV_TIMEOUT,
    CONF_NAV_CONTINUOUS,
    CONF_NAV_CONFIRMATION_SPEECH,
    CONF_BUTTON_ENTITY,
    CONF_BUTTON_TRIGGER,
    DEFAULT_NAV_WAKE_PHRASE,
    DEFAULT_NAV_TIMEOUT,
    DEFAULT_AI_TEMPERATURE,
    DEFAULT_AI_MAX_TOKENS,
    DEFAULT_AI_TIMEOUT,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_PORT,
    DEFAULT_OLLAMA_CONTEXT_SIZE,
    DEFAULT_OLLAMA_KEEP_ALIVE,
    NAV_TIMEOUT_OPTIONS,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


class VoiceJellyfinConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the multi-step config flow."""

    VERSION = 1
    _data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self.async_step_jellyfin(user_input)

    async def async_step_jellyfin(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Jellyfin connection."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        last_input = user_input or {}

        if user_input is not None:
            from .jellyfin.client import JellyfinClient
            from .jellyfin.auth import JellyfinAuth
            test_only = user_input.pop("test_connection", False)
            try:
                auth = JellyfinAuth(
                    url=user_input[CONF_JELLYFIN_URL],
                    api_key=user_input.get(CONF_JELLYFIN_API_KEY, ""),
                )
                client = JellyfinClient(auth)
                await client.async_connect()
                await client.async_close()
                if test_only:
                    description_placeholders["status"] = "✓ Connection successful!"
                else:
                    self._data.update(user_input)
                    return await self.async_step_tv_device()
            except Exception:
                errors["base"] = "cannot_connect"

        _schema = vol.Schema({
            vol.Required(CONF_JELLYFIN_URL, default="http://localhost:8096"): str,
            vol.Optional(CONF_JELLYFIN_API_KEY): str,
            vol.Optional(CONF_JELLYFIN_USERNAME): str,
            vol.Optional(CONF_JELLYFIN_DEFAULT_USER): str,
            vol.Optional("test_connection", default=False): bool,
        })

        return self.async_show_form(
            step_id="jellyfin",
            data_schema=self.add_suggested_values_to_schema(_schema, last_input),
            errors=errors,
            description_placeholders=description_placeholders or None,
        )

    async def async_step_tv_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Choose TV type."""
        if user_input is not None:
            self._data.update(user_input)
            tv_type = user_input.get(CONF_TV_TYPE, TV_TYPE_NONE)
            if tv_type == TV_TYPE_APPLE:
                return await self.async_step_apple_tv()
            if tv_type == TV_TYPE_ANDROID:
                return await self.async_step_android_tv()
            return await self.async_step_ai_provider()

        return self.async_show_form(
            step_id="tv_device",
            data_schema=vol.Schema({
                vol.Required(CONF_TV_TYPE, default=TV_TYPE_NONE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": TV_TYPE_NONE, "label": "No TV / Skip"},
                            {"value": TV_TYPE_APPLE, "label": "Apple TV"},
                            {"value": TV_TYPE_ANDROID, "label": "Android TV / Fire TV"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    async def async_step_apple_tv(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3a: Apple TV remote entity."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_ai_provider()

        return self.async_show_form(
            step_id="apple_tv",
            data_schema=vol.Schema({
                vol.Required(CONF_APPLE_TV_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="remote")
                ),
                vol.Optional(CONF_TV_WAKE_SUPPORT, default=True): bool,
            }),
        )

    async def async_step_android_tv(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3b: Android TV / ADB device."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_ai_provider()

        return self.async_show_form(
            step_id="android_tv",
            data_schema=vol.Schema({
                vol.Optional(CONF_ANDROID_TV_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="media_player")
                ),
                vol.Optional(CONF_ADB_HOST): str,
                vol.Optional(CONF_ADB_PORT, default=5555): int,
                vol.Optional(CONF_TV_WAKE_SUPPORT, default=True): bool,
            }),
        )

    async def async_step_ai_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4: Choose AI provider."""
        if user_input is not None:
            self._data.update(user_input)
            provider = user_input.get(CONF_AI_PROVIDER)
            if provider == AI_PROVIDER_OLLAMA:
                return await self.async_step_ollama()
            if provider in (AI_PROVIDER_OPENAI_COMPAT,):
                return await self.async_step_openai_compat()
            if provider == AI_PROVIDER_HA_CONVERSATION:
                return await self.async_step_nav_mode()
            return await self.async_step_cloud_provider()

        return self.async_show_form(
            step_id="ai_provider",
            data_schema=vol.Schema({
                vol.Required(CONF_AI_PROVIDER, default=AI_PROVIDER_HA_CONVERSATION): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": k, "label": v}
                            for k, v in AI_PROVIDER_LABELS.items()
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    async def async_step_cloud_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4b: Cloud provider credentials (OpenAI / Anthropic / Gemini / OpenRouter)."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_nav_mode()

        return self.async_show_form(
            step_id="cloud_provider",
            data_schema=vol.Schema({
                vol.Required(CONF_AI_API_KEY): str,
                vol.Optional(CONF_AI_MODEL): str,
                vol.Optional(CONF_AI_BASE_URL): str,
                vol.Optional(CONF_AI_TEMPERATURE, default=DEFAULT_AI_TEMPERATURE): vol.Coerce(float),
                vol.Optional(CONF_AI_MAX_TOKENS, default=DEFAULT_AI_MAX_TOKENS): int,
                vol.Optional(CONF_AI_STREAMING, default=True): bool,
                vol.Optional(CONF_AI_TIMEOUT, default=DEFAULT_AI_TIMEOUT): int,
            }),
        )

    async def async_step_ollama(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4c: Ollama local configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Fetch model list to validate connectivity
            try:
                from .ai.providers.ollama import OllamaProvider
                models = await OllamaProvider.async_list_models(
                    host=user_input[CONF_OLLAMA_HOST],
                    port=user_input[CONF_OLLAMA_PORT],
                    https=user_input.get(CONF_OLLAMA_HTTPS, False),
                )
                self._data.update(user_input)
                self._data["_ollama_models"] = models
                return await self.async_step_nav_mode()
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="ollama",
            data_schema=vol.Schema({
                vol.Required(CONF_OLLAMA_HOST, default=DEFAULT_OLLAMA_HOST): str,
                vol.Required(CONF_OLLAMA_PORT, default=DEFAULT_OLLAMA_PORT): int,
                vol.Optional(CONF_OLLAMA_HTTPS, default=False): bool,
                vol.Optional(CONF_OLLAMA_MODEL, default="llama3"): str,
                vol.Optional(CONF_OLLAMA_CONTEXT_SIZE, default=DEFAULT_OLLAMA_CONTEXT_SIZE): int,
                vol.Optional(CONF_OLLAMA_KEEP_ALIVE, default=DEFAULT_OLLAMA_KEEP_ALIVE): str,
                vol.Optional(CONF_AI_STREAMING, default=True): bool,
                vol.Optional(CONF_AI_TIMEOUT, default=DEFAULT_AI_TIMEOUT): int,
            }),
            errors=errors,
        )

    async def async_step_openai_compat(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4d: OpenAI-compatible endpoint (LM Studio, vLLM, custom)."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_nav_mode()

        return self.async_show_form(
            step_id="openai_compat",
            data_schema=vol.Schema({
                vol.Required(CONF_AI_BASE_URL, default="http://localhost:1234/v1"): str,
                vol.Optional(CONF_AI_API_KEY, default="not-needed"): str,
                vol.Optional(CONF_AI_MODEL, default="local-model"): str,
                vol.Optional(CONF_AI_STREAMING, default=True): bool,
                vol.Optional(CONF_AI_TIMEOUT, default=DEFAULT_AI_TIMEOUT): int,
            }),
        )

    async def async_step_nav_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 5: Navigation mode settings."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_accessibility_button()

        return self.async_show_form(
            step_id="nav_mode",
            data_schema=vol.Schema({
                vol.Optional(CONF_NAV_WAKE_PHRASE, default=DEFAULT_NAV_WAKE_PHRASE): str,
                vol.Optional(CONF_NAV_TIMEOUT, default=str(DEFAULT_NAV_TIMEOUT)): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": str(v), "label": k}
                            for k, v in NAV_TIMEOUT_OPTIONS.items()
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(CONF_NAV_CONTINUOUS, default=True): bool,
                vol.Optional(CONF_NAV_CONFIRMATION_SPEECH, default=True): bool,
            }),
        )

    async def async_step_accessibility_button(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 6: Optional physical accessibility button entity."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="Voice Jellyfin",
                data=self._data,
            )

        return self.async_show_form(
            step_id="accessibility_button",
            data_schema=vol.Schema({
                vol.Optional(CONF_BUTTON_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig()
                ),
                vol.Optional(CONF_BUTTON_TRIGGER, default="state_changed"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "state_changed", "label": "State Change (on/off button)"},
                            {"value": "event", "label": "HA Event"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return VoiceJellyfinOptionsFlow(config_entry)


class VoiceJellyfinOptionsFlow(config_entries.OptionsFlow):
    """Options flow for reconfiguration without re-setup."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._entry.options or self._entry.data
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_NAV_TIMEOUT, default=str(current.get(CONF_NAV_TIMEOUT, DEFAULT_NAV_TIMEOUT))): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[{"value": str(v), "label": k} for k, v in NAV_TIMEOUT_OPTIONS.items()],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(CONF_NAV_WAKE_PHRASE, default=current.get(CONF_NAV_WAKE_PHRASE, DEFAULT_NAV_WAKE_PHRASE)): str,
                vol.Optional(CONF_NAV_CONFIRMATION_SPEECH, default=current.get(CONF_NAV_CONFIRMATION_SPEECH, True)): bool,
                vol.Optional(CONF_BUTTON_ENTITY, default=current.get(CONF_BUTTON_ENTITY, "")): str,
            }),
        )
