from typing import Final

DOMAIN: Final = "iqua_softener"

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_DEVICE_SERIAL_NUMBER: Final = "device_sn"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_ENABLE_WEBSOCKET: Final = "enable_websocket"

DEFAULT_UPDATE_INTERVAL: Final = 5  # minutes
DEFAULT_ENABLE_WEBSOCKET: Final = True

# Switch optimistic state timeout (seconds)
SWITCH_OPTIMISTIC_TIMEOUT: Final = 10

VOLUME_FLOW_RATE_LITERS_PER_MINUTE: Final = "L/m"
VOLUME_FLOW_RATE_GALLONS_PER_MINUTE: Final = "gal/m"
