from __future__ import annotations

import logging
from datetime import date, datetime

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ATTRIBUTE_NAMES,
    CONF_CLIENT,
    CONF_EXCLUDE,
    CONF_FLAGDAYS,
    CONF_INCLUDE,
    CONF_OFFSET,
    CONF_SENSORS,
    DEFAULT_ATTRIBUTE_NAMES,
    DEFAULT_DATE_FORMAT,
    DEFAULT_OFFSET,
    DOMAIN,
    KEY_DATE,
    KEY_DATE_END,
    KEY_FLAG,
    KEY_NAME,
    KEY_PRIORITY,
)
from .flagdage_dk import flagdage_dk

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

# YAML is only accepted to be imported once into a config entry.
# (Entries given as strings are sensors/groups of sensors.)
FLAGDAY_SCHEMA = vol.Schema(
    {
        vol.Required(KEY_NAME): cv.string,
        vol.Required(KEY_DATE): cv.string,
        vol.Optional(KEY_DATE_END): cv.string,
        vol.Optional(KEY_FLAG): cv.string,
        vol.Optional(KEY_PRIORITY): vol.Coerce(int),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_OFFSET, default=DEFAULT_OFFSET): vol.All(
                    vol.Coerce(int), vol.Range(min=0)
                ),
                vol.Optional(CONF_INCLUDE, default=[]): vol.All(
                    cv.ensure_list, [cv.string]
                ),
                vol.Optional(CONF_EXCLUDE, default=[]): vol.All(
                    cv.ensure_list, [cv.string]
                ),
                vol.Optional(CONF_ATTRIBUTE_NAMES): vol.All(
                    cv.ensure_list, [cv.string]
                ),
                vol.Optional(CONF_FLAGDAYS, default=[]): vol.All(
                    cv.ensure_list, [vol.Any(FLAGDAY_SCHEMA, cv.string)]
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Import an existing YAML configuration into a config entry.

    Only the current domain name (flagdage_dk) is recognized. A YAML
    block still using the old "flagdays_dk:" key must be renamed to
    "flagdage_dk:" first, since Home Assistant only loads an
    integration for a key that matches an installed component's
    domain.
    """
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=config[DOMAIN],
            )
        )
    return True


def _lower(values) -> list[str]:
    return [str(v).lower() for v in (values or [])]


def _expand_sensors(hass: HomeAssistant, entity_ids: list[str]) -> list[str]:
    """Resolve sensors and groups of sensors into a list of sensor entity ids."""
    result: list[str] = []
    for entity_id in entity_ids:
        domain = entity_id.split(".", 1)[0]
        if domain == "sensor":
            result.append(entity_id)
        elif domain == "group":
            state = hass.states.get(entity_id)
            if state is None:
                continue
            for member in state.attributes.get("entity_id", []):
                if member.split(".", 1)[0] == "sensor":
                    result.append(member)
    return result


def _to_date(value):
    if isinstance(value, (datetime, date)):
        return value
    if isinstance(value, str):
        return dt_util.parse_datetime(value) or dt_util.parse_date(value)
    return None


def _flagday_from_sensor(hass: HomeAssistant, entity_id: str, attr_names: list[str]):
    """Return {name: {date: ...}} from the first attribute holding a date."""
    state = hass.states.get(entity_id)
    if state is None:
        _LOGGER.debug("Sensor %s not available (yet)", entity_id)
        return {}
    for attr_name in attr_names:
        value = _to_date(state.attributes.get(attr_name))
        if value is not None:
            name = state.attributes.get(ATTR_FRIENDLY_NAME, entity_id)
            return {name: {KEY_DATE: value.strftime(DEFAULT_DATE_FORMAT)}}
    _LOGGER.debug("No date attribute %s found in %s", attr_names, entity_id)
    return {}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    cfg = {**entry.data, **entry.options}

    include = _lower(cfg.get(CONF_INCLUDE))
    exclude = _lower(cfg.get(CONF_EXCLUDE))

    flagdays = flagdage_dk(include=include, exclude=exclude)
    _LOGGER.debug("include: %s | exclude: %s", include, exclude)

    # Custom flagdays: {name: {date: ..., priority: ...}}
    customFlagdays = {}
    for item in cfg.get(CONF_FLAGDAYS, []):
        data = dict(item)
        name = data.pop(KEY_NAME)
        data.setdefault(KEY_PRIORITY, 0)
        customFlagdays[name] = data

    # Flagdays from sensors / groups of sensors
    sensors = cfg.get(CONF_SENSORS) or []
    attr_names = _lower(cfg.get(CONF_ATTRIBUTE_NAMES) or DEFAULT_ATTRIBUTE_NAMES)
    for entity_id in _expand_sensors(hass, sensors):
        customFlagdays.update(_flagday_from_sensor(hass, entity_id, attr_names))

    _LOGGER.debug("Adding %s custom flagdays", len(customFlagdays))
    flagdays.add(customFlagdays)

    # The sensors may not exist yet during startup: reload once HA has started
    if sensors and not hass.is_running:

        async def _reload_after_start(_hass: HomeAssistant) -> None:
            if entry.state is ConfigEntryState.LOADED:
                await hass.config_entries.async_reload(entry.entry_id)

        async_at_started(hass, _reload_after_start)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        CONF_CLIENT: flagdays,
        CONF_OFFSET: int(cfg.get(CONF_OFFSET, DEFAULT_OFFSET)),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when the options were changed."""
    await hass.config_entries.async_reload(entry.entry_id)
