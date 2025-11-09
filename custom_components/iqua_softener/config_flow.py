import logging
from typing import Any, Dict, Optional

from homeassistant import config_entries
import voluptuous as vol

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
    VERSION = 1

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        if user_input is not None:
            # Validate that at least one serial number is provided
            device_sn = user_input.get(CONF_DEVICE_SERIAL_NUMBER)
            product_sn = user_input.get(CONF_PRODUCT_SERIAL_NUMBER)
            
            if not device_sn and not product_sn:
                errors["base"] = "missing_serial_number"
            else:
                # Show progress message
                self.async_show_progress(
                    step_id="user",
                    progress_action="validating_credentials"
                )
                
                # Validate authentication and device access
                validation_result = await self._validate_input(user_input)
                
                self.async_show_progress_done(next_step_id="user")
                
                if validation_result["success"]:
                    self.data = user_input
                    # Create a title based on which serial number was provided
                    if device_sn:
                        title = f"iQua Device {device_sn}"
                    else:
                        title = f"iQua Product {product_sn}"
                        
                    return self.async_create_entry(title=title, data=self.data)
                else:
                    errors["base"] = validation_result["error"]

        return self.async_show_form(
            step_id="user", 
            data_schema=DATA_SCHEMA_USER, 
            errors=errors,
            description_placeholders={
                "serial_number_help": "Enter either Device Serial Number OR Product Serial Number (not both)"
            }
        )

    async def _validate_input(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the user input by testing authentication and device access."""
        try:
            # Extract credentials and serial numbers
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            device_sn = user_input.get(CONF_DEVICE_SERIAL_NUMBER)
            product_sn = user_input.get(CONF_PRODUCT_SERIAL_NUMBER)
            
            _LOGGER.info("Validating credentials and device access for user: %s", username)
            
            # Create a test IquaSoftener instance
            test_iqua = IquaSoftener(
                username=username,
                password=password,
                device_serial_number=device_sn,
                product_serial_number=product_sn,
                enable_websocket=False,  # Don't start WebSocket during validation
            )
            
            # Test authentication by attempting to get device data
            device_data = await self.hass.async_add_executor_job(test_iqua.get_data)
            
            if device_data is None:
                _LOGGER.error("Authentication validation failed - no data returned")
                return {"success": False, "error": "no_data"}
            
            _LOGGER.info("Authentication validation successful for user: %s", username)
            return {"success": True, "error": None}
            
        except IquaSoftenerException as err:
            error_msg = str(err).lower()
            _LOGGER.error("Authentication validation failed: %s", err)
            
            # Categorize different types of errors
            if "authentication error" in error_msg or "invalid email or password" in error_msg:
                return {"success": False, "error": "invalid_auth"}
            elif "device" in error_msg and ("not found" in error_msg or "serial" in error_msg):
                return {"success": False, "error": "device_not_found"}
            else:
                return {"success": False, "error": "cannot_connect"}
                
        except Exception as err:
            _LOGGER.error("Unexpected error during validation: %s", err)
            return {"success": False, "error": "unknown"}

    async def async_step_reconfigure(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle reconfiguration of the integration."""
        config_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors: Dict[str, str] = {}
        
        if user_input is not None:
            # Validate that at least one serial number is provided
            device_sn = user_input.get(CONF_DEVICE_SERIAL_NUMBER)
            product_sn = user_input.get(CONF_PRODUCT_SERIAL_NUMBER)
            
            if not device_sn and not product_sn:
                errors["base"] = "missing_serial_number"
            else:
                # Show progress message
                self.async_show_progress(
                    step_id="reconfigure",
                    progress_action="validating_credentials"
                )
                
                # Validate authentication and device access
                validation_result = await self._validate_input(user_input)
                
                self.async_show_progress_done(next_step_id="reconfigure")
                
                if validation_result["success"]:
                    # Update the config entry
                    return self.async_update_reload_and_abort(
                        config_entry, data=user_input
                    )
                else:
                    errors["base"] = validation_result["error"]

        # Pre-fill form with existing data
        current_data = config_entry.data
        default_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=current_data.get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD, default=current_data.get(CONF_PASSWORD, "")): str,
                vol.Optional(CONF_DEVICE_SERIAL_NUMBER, default=current_data.get(CONF_DEVICE_SERIAL_NUMBER, "")): str,
                vol.Optional(CONF_PRODUCT_SERIAL_NUMBER, default=current_data.get(CONF_PRODUCT_SERIAL_NUMBER, "")): str,
                vol.Optional(CONF_UPDATE_INTERVAL, default=current_data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=60)
                ),
                vol.Optional(CONF_ENABLE_WEBSOCKET, default=current_data.get(CONF_ENABLE_WEBSOCKET, DEFAULT_ENABLE_WEBSOCKET)): bool,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=default_schema,
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
