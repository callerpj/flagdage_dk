from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_ATTRIBUTE_NAMES,
    CONF_EXCLUDE,
    CONF_FLAGDAYS,
    CONF_INCLUDE,
    CONF_OFFSET,
    CONF_SENSORS,
    DEFAULT_ATTRIBUTE_NAMES,
    DEFAULT_OFFSET,
    DOMAIN,
    KEY_DATE,
    KEY_DATE_END,
    KEY_FLAG,
    KEY_NAME,
    KEY_PRIORITY,
)

_LOGGER = logging.getLogger(__name__)

CONF_ADD_ANOTHER = "add_another"
CONF_REMOVE = "remove"
CONF_EXCLUDE_CUSTOM = "exclude_custom"

INCLUDE_SUGGESTIONS = ["Erfalasorput", "Merkið", "Færøerne", "Grønland"]
# Predefined exclude options (shown as checkboxes)
EXCLUDE_PRESETS = ["Kongelige", "Udsendte", "Religiøs", "all"]


def _split_exclude(values: list[str] | None) -> tuple[list[str], list[str]]:
    """Split stored exclude values into (checked presets, manual values)."""
    presets = {p.lower(): p for p in EXCLUDE_PRESETS}
    selected: list[str] = []
    custom: list[str] = []
    for value in values or []:
        preset = presets.get(str(value).lower())
        if preset:
            if preset not in selected:
                selected.append(preset)
        else:
            custom.append(str(value))
    return selected, custom


def _valid_date(value: str) -> bool:
    """Accept 'd-m' or 'd-m-YYYY' (leading zeros optional)."""
    value = value.strip()
    try:
        if value.count("-") == 2:
            datetime.strptime(value, "%d-%m-%Y")
        elif value.count("-") == 1:
            datetime.strptime(f"{value}-2000", "%d-%m-%Y")  # 2000 = leap year
        else:
            return False
    except ValueError:
        return False
    return True


def _valid_day_month(value: str) -> bool:
    """Only 'd-m' (no year), as needed for the end of a prolonged flagday."""
    return value.count("-") == 1 and _valid_date(value)


def _month_day(value: str) -> tuple[int, int]:
    """(month, day) of a 'd-m' or 'd-m-YYYY' string, for comparing."""
    parts = value.strip().split("-")
    return int(parts[1]), int(parts[0])


def _flagday_label(flagday: dict[str, Any]) -> str:
    label = f"{flagday[KEY_NAME]} ({flagday[KEY_DATE]}"
    if flagday.get(KEY_DATE_END):
        label += f" – {flagday[KEY_DATE_END]}"
    if flagday.get(KEY_FLAG):
        label += f", {flagday[KEY_FLAG]}"
    return label + ")"


def _tag_selector(suggestions: list[str]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=suggestions,
            multiple=True,
            custom_value=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _settings_schema(defaults: dict[str, Any]) -> vol.Schema:
    selected, custom = _split_exclude(defaults.get(CONF_EXCLUDE, []))
    return vol.Schema(
        {
            vol.Required(
                CONF_OFFSET, default=defaults.get(CONF_OFFSET, DEFAULT_OFFSET)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=240,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
            vol.Optional(
                CONF_INCLUDE, default=defaults.get(CONF_INCLUDE, [])
            ): _tag_selector(INCLUDE_SUGGESTIONS),
            vol.Optional(CONF_EXCLUDE, default=selected): SelectSelector(
                SelectSelectorConfig(
                    options=EXCLUDE_PRESETS,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(CONF_EXCLUDE_CUSTOM, default=custom): TextSelector(
                TextSelectorConfig(multiple=True)
            ),
        }
    )


def _clean_settings(user_input: dict[str, Any]) -> dict[str, Any]:
    # Checked presets + manual values are stored together in one list
    # (a YAML import puts everything into "exclude", which works the same).
    exclude: list[str] = []
    for value in user_input.get(CONF_EXCLUDE, []) + user_input.get(
        CONF_EXCLUDE_CUSTOM, []
    ):
        value = str(value).strip()
        if value and value.lower() not in (e.lower() for e in exclude):
            exclude.append(value)
    return {
        CONF_OFFSET: int(user_input.get(CONF_OFFSET, DEFAULT_OFFSET)),
        CONF_INCLUDE: [s.strip() for s in user_input.get(CONF_INCLUDE, []) if s.strip()],
        CONF_EXCLUDE: exclude,
    }


def _split_import_flagdays(
    items: list[Any] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Split YAML flagdays into (name/date dicts, sensor/group entity ids)."""
    flagdays: list[dict[str, Any]] = []
    sensors: list[str] = []
    for item in items or []:
        if isinstance(item, str):
            if item.split(".", 1)[0] in ("sensor", "group"):
                sensors.append(item)
            else:
                _LOGGER.warning("Skipping unsupported flagday on import: %s", item)
            continue
        if not isinstance(item, dict) or KEY_NAME not in item or KEY_DATE not in item:
            _LOGGER.warning("Skipping unsupported flagday on import: %s", item)
            continue
        flagday = {KEY_NAME: str(item[KEY_NAME]), KEY_DATE: str(item[KEY_DATE])}
        if KEY_DATE_END in item:
            flagday[KEY_DATE_END] = str(item[KEY_DATE_END])
        if KEY_FLAG in item:
            flagday[KEY_FLAG] = str(item[KEY_FLAG])
        if KEY_PRIORITY in item:
            flagday[KEY_PRIORITY] = int(item[KEY_PRIORITY])
        flagdays.append(flagday)
    return flagdays, sensors


class FlagdaysConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FlagdaysOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            data = _clean_settings(user_input)
            data[CONF_FLAGDAYS] = []
            return self.async_create_entry(title="Flagdays DK", data=data)

        return self.async_show_form(step_id="user", data_schema=_settings_schema({}))

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import from configuration.yaml (only once)."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        data = _clean_settings(import_data)
        flagdays, sensors = _split_import_flagdays(import_data.get(CONF_FLAGDAYS))
        data[CONF_FLAGDAYS] = flagdays
        data[CONF_SENSORS] = sensors
        data[CONF_ATTRIBUTE_NAMES] = list(
            import_data.get(CONF_ATTRIBUTE_NAMES) or DEFAULT_ATTRIBUTE_NAMES
        )
        return self.async_create_entry(title="Flagdays DK", data=data)


class FlagdaysOptionsFlow(OptionsFlow):
    """Change settings, add and remove custom flagdays."""

    def __init__(self) -> None:
        self._options: dict[str, Any] | None = None

    @property
    def _opts(self) -> dict[str, Any]:
        if self._options is None:
            self._options = {**self.config_entry.data, **self.config_entry.options}
            self._options[CONF_FLAGDAYS] = list(self._options.get(CONF_FLAGDAYS, []))
        return self._options

    def _save(self) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=self._opts)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "add_flagday", "remove_flagday", "sensors"],
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._opts.update(_clean_settings(user_input))
            return self._save()
        return self.async_show_form(
            step_id="settings", data_schema=_settings_schema(self._opts)
        )

    async def async_step_add_flagday(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        schema = vol.Schema(
            {
                vol.Required(KEY_NAME): TextSelector(),
                vol.Required(KEY_DATE): TextSelector(),
                vol.Optional(KEY_DATE_END): TextSelector(),
                vol.Optional(KEY_FLAG): TextSelector(),
                vol.Optional(CONF_ADD_ANOTHER, default=False): BooleanSelector(),
            }
        )

        if user_input is not None:
            name = user_input[KEY_NAME].strip()
            date = user_input[KEY_DATE].strip()
            date_end = (user_input.get(KEY_DATE_END) or "").strip()
            flag = (user_input.get(KEY_FLAG) or "").strip()
            existing = {f[KEY_NAME].lower() for f in self._opts[CONF_FLAGDAYS]}

            if not name:
                errors[KEY_NAME] = "name_required"
            elif name.lower() in existing:
                errors[KEY_NAME] = "name_exists"
            if not _valid_date(date):
                errors[KEY_DATE] = "invalid_date"
            if date_end:
                if not _valid_day_month(date_end):
                    errors[KEY_DATE_END] = "invalid_date_end"
                elif KEY_DATE not in errors and _month_day(date_end) < _month_day(date):
                    errors[KEY_DATE_END] = "date_end_before_start"

            if not errors:
                flagday = {KEY_NAME: name, KEY_DATE: date}
                if date_end:
                    flagday[KEY_DATE_END] = date_end
                if flag:
                    flagday[KEY_FLAG] = flag
                self._opts[CONF_FLAGDAYS].append(flagday)
                if user_input.get(CONF_ADD_ANOTHER):
                    user_input = None  # empty form for the next flagday
                else:
                    return self._save()

        return self.async_show_form(
            step_id="add_flagday",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_remove_flagday(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        flagdays = self._opts[CONF_FLAGDAYS]
        if not flagdays:
            return self.async_abort(reason="no_flagdays")

        if user_input is not None:
            remove = set(user_input[CONF_REMOVE])
            self._opts[CONF_FLAGDAYS] = [
                f for f in flagdays if f[KEY_NAME] not in remove
            ]
            return self._save()

        options = [
            SelectOptionDict(value=f[KEY_NAME], label=_flagday_label(f))
            for f in flagdays
        ]
        return self.async_show_form(
            step_id="remove_flagday",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REMOVE): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sensors (or groups of sensors) as source for flagdays."""
        if user_input is not None:
            attr_names = [
                a.strip() for a in user_input.get(CONF_ATTRIBUTE_NAMES, []) if a.strip()
            ]
            self._opts[CONF_SENSORS] = user_input.get(CONF_SENSORS, [])
            self._opts[CONF_ATTRIBUTE_NAMES] = attr_names or list(
                DEFAULT_ATTRIBUTE_NAMES
            )
            return self._save()

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SENSORS, default=self._opts.get(CONF_SENSORS, [])
                    ): EntitySelector(
                        EntitySelectorConfig(domain=["sensor", "group"], multiple=True)
                    ),
                    vol.Optional(
                        CONF_ATTRIBUTE_NAMES,
                        default=self._opts.get(
                            CONF_ATTRIBUTE_NAMES, list(DEFAULT_ATTRIBUTE_NAMES)
                        ),
                    ): TextSelector(TextSelectorConfig(multiple=True)),
                }
            ),
        )
