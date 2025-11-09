import logging
from typing import Any, Dict, Optional

from homeassistant import config_entries
import voluptuous as vol

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

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA_USER = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_DEVICE_SERIAL_NUMBER): str,
        vol.Optional(CONF_PRODUCT_SERIAL_NUMBER): str,
        vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=60)
        ),
        vol.Optional(CONF_ENABLE_WEBSOCKET, default=DEFAULT_ENABLE_WEBSOCKET): bool,
    }
)


class IquaSoftenerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    data: Optional[Dict[str, Any]]

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        if user_input is not None:
            # Validate that at least one serial number is provided
            device_sn = user_input.get(CONF_DEVICE_SERIAL_NUMBER)
            product_sn = user_input.get(CONF_PRODUCT_SERIAL_NUMBER)
            
            if not device_sn and not product_sn:
                errors["base"] = "missing_serial_number"
            else:
                self.data = user_input
                # Create a title based on which serial number was provided
                if device_sn:
                    title = f"iQua Device {device_sn}"
                else:
                    title = f"iQua Product {product_sn}"
                    
                return self.async_create_entry(title=title, data=self.data)

        return self.async_show_form(
            step_id="user", 
            data_schema=DATA_SCHEMA_USER, 
            errors=errors,
            description_placeholders={
                "serial_number_help": "Enter either Device Serial Number OR Product Serial Number (not both)"
            }
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return IquaSoftenerOptionsFlowHandler()


class IquaSoftenerOptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_UPDATE_INTERVAL,
                        self.config_entry.data.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Optional(
                    CONF_ENABLE_WEBSOCKET,
                    default=self.config_entry.options.get(
                        CONF_ENABLE_WEBSOCKET,
                        self.config_entry.data.get(
                            CONF_ENABLE_WEBSOCKET, DEFAULT_ENABLE_WEBSOCKET
                        ),
                    ),
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
