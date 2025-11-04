from typing import Final

DOMAIN: Final = "iqua_softener"

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_DEVICE_SERIAL_NUMBER: Final = "device_sn"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_ENABLE_WEBSOCKET: Final = "enable_websocket"
CONF_API_BASE_URL: Final = "api_base_url"
CONF_WEBSOCKET_BASE_URL: Final = "websocket_base_url"

DEFAULT_UPDATE_INTERVAL: Final = 5  # minutes
DEFAULT_ENABLE_WEBSOCKET: Final = True

# API Configuration
IQUA_API_BASE_URL: Final = "https://api.myiquaapp.com"
IQUA_WEBSOCKET_BASE_URL: Final = "wss://api.myiquaapp.com"

VOLUME_FLOW_RATE_LITERS_PER_MINUTE: Final = "L/m"
VOLUME_FLOW_RATE_GALLONS_PER_MINUTE: Final = "gal/m"
