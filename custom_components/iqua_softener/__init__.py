import logging

from homeassistant import config_entries, core
from homeassistant.exceptions import ConfigEntryNotReady
from .vendor.iqua_softener import IquaSoftener, IquaSoftenerException

from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE_SERIAL_NUMBER,
    CONF_PRODUCT_SERIAL_NUMBER,
    CONF_UPDATE_INTERVAL,
    CONF_ENABLE_WEBSOCKET,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_ENABLE_WEBSOCKET,
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

    _LOGGER.info("Configuration data: %s", hass_data)
    _LOGGER.info("Entry data: %s", entry.data)
    _LOGGER.info("Entry options: %s", entry.options)

    # Create shared coordinator
    update_interval_minutes = hass_data.get(
        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
    )
    enable_websocket = hass_data.get(CONF_ENABLE_WEBSOCKET, DEFAULT_ENABLE_WEBSOCKET)
    _LOGGER.info(
        "Creating coordinator with update interval: %d minutes, WebSocket: %s",
        update_interval_minutes,
        enable_websocket,
    )
    # Extract serial numbers from config
    device_sn = hass_data.get(CONF_DEVICE_SERIAL_NUMBER)
    product_sn = hass_data.get(CONF_PRODUCT_SERIAL_NUMBER)
    
    _LOGGER.info("Creating IquaSoftener with device_sn=%s, product_sn=%s", device_sn, product_sn)
    
    # Create coordinator (authentication already validated in config flow)
    coordinator = IquaSoftenerCoordinator(
        hass,
        IquaSoftener(
            hass_data[CONF_USERNAME],
            hass_data[CONF_PASSWORD],
            device_serial_number=device_sn,
            product_serial_number=product_sn,
            enable_websocket=enable_websocket,  # Let the library handle WebSocket
        ),
        update_interval_minutes,
        enable_websocket,
        hass_data,  # Pass config data for URL configuration
    )

    # Perform initial data fetch for immediate availability
    try:
        _LOGGER.info("Performing initial data fetch...")
        await coordinator.async_config_entry_first_refresh()
        
        if coordinator.data is None:
            _LOGGER.warning("Initial data fetch returned no data, but continuing setup")
        else:
            _LOGGER.info("Initial data fetch successful")
            
    except Exception as err:
        _LOGGER.warning("Initial data fetch failed, but continuing setup: %s", err)
        # Don't fail the entire setup if initial fetch fails - the coordinator will retry

    unsub_options_update_listener = entry.add_update_listener(options_update_listener)
    hass_data["unsub_options_update_listener"] = unsub_options_update_listener
    hass_data["coordinator"] = coordinator
    hass.data[DOMAIN][entry.entry_id] = hass_data

    # Start the WebSocket connection for real-time data (if enabled)
    if enable_websocket:
        _LOGGER.info("WebSocket is enabled, starting library's WebSocket connection...")
        await coordinator.async_start_websocket()
    else:
        _LOGGER.info("WebSocket is disabled in configuration")

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "switch"])
    return True


async def options_update_listener(
    hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry
):
    _LOGGER.info("Options updated, reloading integration")
    # Stop WebSocket before reload
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    await coordinator.async_stop_websocket()

    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    # Stop the WebSocket connection
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    await coordinator.async_stop_websocket()

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["sensor", "switch"]
    )

    hass.data[DOMAIN][entry.entry_id]["unsub_options_update_listener"]()

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
