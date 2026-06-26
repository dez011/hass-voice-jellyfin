"""Root conftest — stubs out homeassistant package so unit tests run
without a full HA install. Tests that need real HA behaviour should use
pytest-homeassistant-custom-component in CI instead."""
from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock


def _make_module(name: str, **attrs: object) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# ── homeassistant core ────────────────────────────────────────────────────────

_ha = _make_module("homeassistant")
_ha_core = _make_module("homeassistant.core", HomeAssistant=MagicMock, callback=lambda f: f, ServiceCall=MagicMock)
_ha_const = _make_module("homeassistant.const", Platform=MagicMock(), EVENT_STATE_CHANGED="state_changed")

# config_entries
class _ConfigEntry:
    def __init__(self, *a, **kw): pass
class _OptionsFlow:
    pass
class _ConfigFlow:
    VERSION = 1
    def __init_subclass__(cls, domain=None, **kw):
        super().__init_subclass__(**kw)
    def async_show_form(self, **kw): return kw
    def async_create_entry(self, **kw): return kw
_ce_mod = _make_module(
    "homeassistant.config_entries",
    ConfigEntry=_ConfigEntry,
    ConfigFlow=_ConfigFlow,
    OptionsFlow=_OptionsFlow,
    SOURCE_USER="user",
)
_ce_mod.callback = lambda f: f

# data_entry_flow
_make_module("homeassistant.data_entry_flow", FlowResult=dict)

# helpers
_make_module("homeassistant.helpers")
class _DataUpdateCoordinator:
    def __init__(self, hass=None, logger=None, name=None, update_interval=None): pass
    async def async_refresh(self): pass
    def async_set_updated_data(self, data): pass
    def __init_subclass__(cls, **kw): super().__init_subclass__(**kw)
    def __class_getitem__(cls, _): return cls

class _CoordinatorEntity:
    def __init__(self, coordinator): self.coordinator = coordinator
    def __class_getitem__(cls, _): return cls
    def async_write_ha_state(self): pass

_make_module("homeassistant.helpers.update_coordinator",
             DataUpdateCoordinator=_DataUpdateCoordinator,
             UpdateFailed=Exception,
             CoordinatorEntity=_CoordinatorEntity)
_make_module("homeassistant.helpers.entity_platform", AddEntitiesCallback=MagicMock)
_make_module("homeassistant.helpers.config_validation",
             string=str, boolean=bool, positive_int=int,
             PLATFORM_SCHEMA=MagicMock())
_make_module("homeassistant.helpers.storage", Store=MagicMock)
_make_module("homeassistant.helpers.entity", Entity=object)
_make_module("homeassistant.helpers.selector",
             selector=MagicMock(),
             SelectSelector=MagicMock(),
             SelectSelectorConfig=MagicMock(),
             SelectSelectorMode=MagicMock(),
             EntitySelector=MagicMock(),
             EntitySelectorConfig=MagicMock())

# components
_make_module("homeassistant.components")
_make_module("homeassistant.components.sensor", SensorEntity=object)
_make_module("homeassistant.components.switch", SwitchEntity=object)
_make_module("homeassistant.components.select", SelectEntity=object)

# exceptions
_make_module("homeassistant.exceptions", HomeAssistantError=Exception)

# voluptuous (used in config_flow)
try:
    import voluptuous  # noqa: F401 — already installed via pytest-asyncio dep tree
except ImportError:
    _make_module("voluptuous",
                 Schema=MagicMock(side_effect=lambda s: s),
                 Required=MagicMock(side_effect=lambda k, **_: k),
                 Optional=MagicMock(side_effect=lambda k, **_: k),
                 Coerce=MagicMock(side_effect=lambda t: t))
