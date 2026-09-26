from __future__ import annotations

from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import sun

from homeassistant.const import ATTR_ATTRIBUTION, ATTR_DATE, ATTR_DEVICE_CLASS

from .const import (
    CONF_CLIENT,
    CONF_OFFSET,
    CONF_PLATFORM,
    CREDITS,
    DOMAIN,
    UPDATE_INTERVAL,
)

ATTR_CONCURRENT = "concurrent_flagdays"
ATTR_DATE_END = "date_end"
ATTR_DAYS = "days"
ATTR_FLAG = "flag"
ATTR_FLAGDAY_NAME = "flagday_name"
ATTR_FLAG_DOWN = "flag_down_time"
ATTR_FLAG_UP = "flag_up_time"
ATTR_HALF_MAST = "half_mast"
ATTR_YEARS = "years"

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER: logging.Logger = logging.getLogger(__package__)
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    flagdays = data[CONF_CLIENT]
    seen_year = datetime.now().year

    # Define a update function
    async def async_update_data():
        nonlocal seen_year

        # Call, and wait for it to finish, the function with the refresh procedure
        result = await hass.async_add_executor_job(flagdays.update)

        # New year: reload the whole config entry so the regular flagdays
        # (incl. Easter-based ones) and the custom/sensor flagdays are all
        # rebuilt for the new year, instead of just running dry once the
        # next-year fallback entry has passed too.
        current_year = datetime.now().year
        if current_year != seen_year:
            seen_year = current_year
            _LOGGER.info(
                "New year detected, reloading %s to rebuild the flagday list",
                DOMAIN,
            )
            hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

        return result

    # Create a coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=CONF_PLATFORM,
        update_method=async_update_data,
        update_interval=timedelta(minutes=UPDATE_INTERVAL),
    )

    # Immediate refresh
    await coordinator.async_config_entry_first_refresh()

    # Add the sensor to Home Assistant
    async_add_entities([FlagDaysSensor(hass, coordinator, flagdays, data[CONF_OFFSET])])


class FlagDaysSensor(SensorEntity):
    def __init__(self, hass, coordinator, flagdays, offset) -> None:
        self.hass = hass
        self._offset = offset
        self.coordinator = coordinator
        self.flagdays = flagdays
        self.flagUpTime, self.flagDownTime = 0, 0

    @property
    def nextFlagday(self):
        """Always the currently next flagday (None if there is none)."""
        return self.flagdays.flagdays[0] if self.flagdays.flagdays else None

    @property
    def name(self):
        return DOMAIN

    @property
    def icon(self):
        return "mdi:flag"

    @property
    def state(self):
        if self.nextFlagday is None:
            return None
        geo = Observer(
            self.hass.config.latitude,
            self.hass.config.longitude,
            self.hass.config.elevation,
        )
        tzinf=ZoneInfo(key='Europe/Copenhagen')
        s = sun(geo, date=self.nextFlagday.date, tzinfo=tzinf)
        self.flagUpTime = (
            s["sunrise"].replace(hour=8, minute=0, second=0)
            if s["sunrise"].hour < 8
            else s["sunrise"]
        )
        self.flagDownTime = s["sunset"]

        dt_now = datetime.now().astimezone(tzinf)
        _LOGGER.debug(f"Now: {dt_now}")
        offset = timedelta(minutes=self._offset)
        _LOGGER.debug(f"flagUpTime: {self.flagUpTime}")
        if self.flagUpTime > dt_now:
            return self.flagUpTime - offset
        elif (
            type(self.nextFlagday.halfMast) is datetime
            and self.nextFlagday.halfMast.timestamp() > dt_now.timestamp()
        ):
            return self.nextFlagday.halfMast - offset
        else:
            return self.flagDownTime - offset

    @property
    def unique_id(self):
        return "2b5bde57971b4061a6e83f83c141a534"

    @property
    def extra_state_attributes(self):
        if self.nextFlagday is None:
            return {
                ATTR_FLAGDAY_NAME: None,
                ATTR_DAYS: None,
                "future_flagdays": [],
                ATTR_DEVICE_CLASS: "timestamp",
                ATTR_ATTRIBUTION: CREDITS,
            }
        attr = {
            ATTR_FLAGDAY_NAME: self.nextFlagday.name,
            ATTR_DAYS: self.flagdays.days,
            ATTR_YEARS: self.nextFlagday.years,
            ATTR_FLAG: self.nextFlagday.flag,
            ATTR_FLAG_UP: self.flagUpTime.strftime("%H:%M"),
            ATTR_FLAG_DOWN: self.flagDownTime.strftime("%H:%M"),
            ATTR_HALF_MAST: self.nextFlagday.halfMast,
            ATTR_CONCURRENT: self.flagdays.getConcurrentFlagdays(self.nextFlagday.date),
        }
        attr["future_flagdays"] = []
        for flagday in self.flagdays.getFutureFlagdays():
            attr["future_flagdays"].append(
                {
                    ATTR_FLAGDAY_NAME: flagday.name,
                    ATTR_DATE: flagday.getDate("%-d-%-m"),
                    ATTR_DATE_END: flagday.getDateEnd("%-d-%-m"),
                }
            )
        attr.update({ATTR_DEVICE_CLASS: "timestamp", ATTR_ATTRIBUTION: CREDITS})
        return attr

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_update(self):
        """Update the entity. Only used by the generic entity update service."""
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
