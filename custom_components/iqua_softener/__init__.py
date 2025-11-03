import logging

from homeassistant import config_entries, core
from iqua_softener import IquaSoftener

from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE_SERIAL_NUMBER,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
)
from .sensor import IquaSoftenerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass_data = dict(entry.data)
    if entry.options:
        hass_data.update(entry.options)

    # Create shared coordinator
    update_interval_minutes = hass_data.get(
        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
    )
    coordinator = IquaSoftenerCoordinator(
        hass,
        IquaSoftener(
            hass_data[CONF_USERNAME],
            hass_data[CONF_PASSWORD],
            hass_data[CONF_DEVICE_SERIAL_NUMBER],
        ),
        update_interval_minutes,
    )

    unsub_options_update_listener = entry.add_update_listener(options_update_listener)
    hass_data["unsub_options_update_listener"] = unsub_options_update_listener
    hass_data["coordinator"] = coordinator
    hass.data[DOMAIN][entry.entry_id] = hass_data

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "switch")
    )
    return True


async def options_update_listener(
    hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry
):
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    unload_ok = unload_ok and await hass.config_entries.async_forward_entry_unload(
        entry, "switch"
    )

    hass.data[DOMAIN][entry.entry_id]["unsub_options_update_listener"]()

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
