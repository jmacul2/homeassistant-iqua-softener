from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import logging
from typing import Optional, Any

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
    CoordinatorEntity,
)
from homeassistant.util import dt as dt_util

from .vendor.iqua_softener import (
    IquaSoftener,
    IquaSoftenerData,
    IquaSoftenerVolumeUnit,
    IquaSoftenerException,
)

from homeassistant import config_entries, core
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
    SensorEntityDescription,
)
from homeassistant.const import PERCENTAGE
from homeassistant.const import UnitOfVolume

from .const import (
    DOMAIN,
    CONF_DEVICE_SERIAL_NUMBER,
    CONF_PRODUCT_SERIAL_NUMBER,
    DEFAULT_UPDATE_INTERVAL,
    VOLUME_FLOW_RATE_LITERS_PER_MINUTE,
    VOLUME_FLOW_RATE_GALLONS_PER_MINUTE,
)

_LOGGER = logging.getLogger(__name__)


async def _check_water_shutoff_valve_available(coordinator) -> bool:
    """Check if the device has a water shutoff valve installed."""
    try:
        # Use the library method to check if device has water shutoff valve
        has_valve = await coordinator.hass.async_add_executor_job(
            coordinator._iqua_softener.has_water_shutoff_valve
        )
        _LOGGER.debug("Water shutoff valve availability check: %s", has_valve)
        return has_valve
        
    except Exception as err:
        _LOGGER.error("Error checking water shutoff valve availability: %s", err)
        return False


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    config = hass.data[DOMAIN][config_entry.entry_id]
    if config_entry.options:
        config.update(config_entry.options)
    
    # Get device serial number for entity naming (prefer device_sn, fallback to product_sn)
    device_serial_number = config.get(CONF_DEVICE_SERIAL_NUMBER) or config.get(CONF_PRODUCT_SERIAL_NUMBER)
    if not device_serial_number:
        _LOGGER.error("No device or product serial number found in config")
        return

    # Use the shared coordinator from __init__.py
    coordinator = config["coordinator"]
    
    # Authentication is already validated in __init__.py, so coordinator.data should be available
    if coordinator.data is None:
        _LOGGER.error("No data available from coordinator - authentication may have failed")
        return

    # Define all sensors except water shutoff valve state (which is conditional)
    base_sensors = [
        clz(coordinator, device_serial_number, entity_description)
        for clz, entity_description in (
            (
                IquaSoftenerStateSensor,
                SensorEntityDescription(key="State", name="State"),
            ),
            (
                IquaSoftenerDeviceDateTimeSensor,
                SensorEntityDescription(
                    key="DATE_TIME",
                    name="Date/time",
                    icon="mdi:clock",
                ),
            ),
            (
                IquaSoftenerLastRegenerationSensor,
                SensorEntityDescription(
                    key="LAST_REGENERATION",
                    name="Last regeneration",
                    device_class=SensorDeviceClass.TIMESTAMP,
                ),
            ),
            (
                IquaSoftenerOutOfSaltEstimatedDaySensor,
                SensorEntityDescription(
                    key="OUT_OF_SALT_ESTIMATED_DAY",
                    name="Out of salt estimated day",
                    device_class=SensorDeviceClass.TIMESTAMP,
                ),
            ),
            (
                IquaSoftenerSaltLevelSensor,
                SensorEntityDescription(
                    key="SALT_LEVEL",
                    name="Salt level",
                    state_class=SensorStateClass.MEASUREMENT,
                    native_unit_of_measurement=PERCENTAGE,
                ),
            ),
            (
                IquaSoftenerAvailableWaterSensor,
                SensorEntityDescription(
                    key="AVAILABLE_WATER",
                    name="Available water",
                    state_class=SensorStateClass.TOTAL,
                    device_class=SensorDeviceClass.WATER,
                    icon="mdi:water",
                ),
            ),
            (
                IquaSoftenerWaterCurrentFlowSensor,
                SensorEntityDescription(
                    key="WATER_CURRENT_FLOW",
                    name="Water current flow",
                    state_class=SensorStateClass.MEASUREMENT,
                    icon="mdi:water-pump",
                ),
            ),
            (
                IquaSoftenerWaterUsageTodaySensor,
                SensorEntityDescription(
                    key="WATER_USAGE_TODAY",
                    name="Today water usage",
                    state_class=SensorStateClass.TOTAL_INCREASING,
                    device_class=SensorDeviceClass.WATER,
                    icon="mdi:water-minus",
                ),
            ),
            (
                IquaSoftenerWaterUsageDailyAverageSensor,
                SensorEntityDescription(
                    key="WATER_USAGE_DAILY_AVERAGE",
                    name="Water usage daily average",
                    state_class=SensorStateClass.MEASUREMENT,
                    icon="mdi:water-circle",
                ),
            ),
        )
    ]
    
    # Check if device has water shutoff valve and add the sensor conditionally
    has_valve = await _check_water_shutoff_valve_available(coordinator)
    if has_valve:
        _LOGGER.info("Device has water shutoff valve - adding valve state sensor")
        valve_sensor = IquaSoftenerWaterShutoffValveStateSensor(
            coordinator, 
            device_serial_number, 
            SensorEntityDescription(
                key="WATER_SHUTOFF_VALVE_STATE",
                name="Water shutoff valve state",
                icon="mdi:valve",
            )
        )
        base_sensors.append(valve_sensor)
    else:
        _LOGGER.info("Device does not have water shutoff valve - skipping valve state sensor")
    
    sensors = base_sensors
    
    # Add sensors to Home Assistant
    async_add_entities(sensors)
    
    # Force immediate update of all sensors with current data
    if coordinator.data is not None:
        _LOGGER.info("Initializing sensor values immediately with current data...")
        for sensor in sensors:
            try:
                sensor.update(coordinator.data)
                sensor.async_write_ha_state()
            except Exception as err:
                _LOGGER.error("Error initializing sensor %s: %s", sensor.entity_description.name, err)
        _LOGGER.info("All sensors initialized with immediate values")
    else:
        _LOGGER.warning("No data available for immediate sensor initialization")


class IquaSoftenerCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass: core.HomeAssistant,
        iqua_softener: IquaSoftener,
        update_interval_minutes: int = DEFAULT_UPDATE_INTERVAL,
        enable_websocket: bool = True,
        config_data: dict = None,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="Iqua Softener",
            update_interval=timedelta(minutes=update_interval_minutes),
        )
        self._iqua_softener = iqua_softener
        self._enable_websocket = enable_websocket
        self._config_data = config_data or {}

        # Store credentials for authentication recovery
        self._username = self._config_data.get("username")
        self._password = self._config_data.get("password")
        self._device_serial_number = self._config_data.get("device_sn")
        self._product_serial_number = self._config_data.get("product_sn")

        # Flag to delay WebSocket start until after bootstrap
        self._websocket_start_delayed = False

        _LOGGER.info(
            "IquaSoftenerCoordinator initialized with %d minute update interval, WebSocket: %s",
            update_interval_minutes,
            enable_websocket,
        )

    async def async_start_websocket(self):
        """Start the WebSocket connection using library's implementation."""
        if not self._enable_websocket:
            _LOGGER.info("WebSocket disabled, skipping connection")
            return

        try:
            _LOGGER.info("Starting WebSocket using library's built-in implementation...")
            await self.hass.async_add_executor_job(self._iqua_softener.start_websocket)
            _LOGGER.info("WebSocket started successfully using library")
        except Exception as err:
            _LOGGER.error("Failed to start library WebSocket: %s", err)

    async def async_restart_websocket(self):
        """Restart the WebSocket connection."""
        _LOGGER.info("Restarting WebSocket connection")
        await self.async_stop_websocket()
        await self.async_start_websocket()

    async def async_stop_websocket(self):
        """Stop the WebSocket connection using library's implementation."""
        try:
            _LOGGER.info("Stopping WebSocket using library...")
            await self.hass.async_add_executor_job(self._iqua_softener.stop_websocket)
            _LOGGER.info("WebSocket stopped using library")
        except Exception as err:
            _LOGGER.error("Failed to stop library WebSocket: %s", err)

    async def async_retry_websocket(self):
        """Manually retry WebSocket connection."""
        _LOGGER.info("Manual WebSocket retry requested")
        await self.async_restart_websocket()

    async def async_force_update(self):
        """Force an immediate data update and sensor refresh."""
        _LOGGER.info("Manual data refresh requested - forcing API call and sensor updates")
        try:
            await self.async_refresh()
            _LOGGER.info("Manual data refresh completed successfully")
        except Exception as err:
            _LOGGER.error("Manual data refresh failed: %s", err)

    async def _async_update_data(self) -> IquaSoftenerData:
        _LOGGER.debug("Starting data fetch from iQua API...")
        
        # Start WebSocket after first successful data fetch (post-bootstrap)
        if (self._enable_websocket and 
            not self._websocket_start_delayed):
            _LOGGER.info("Starting WebSocket after successful initial API fetch...")
            self._websocket_start_delayed = True
            # Schedule WebSocket start as a background task to avoid blocking data fetch
            self.hass.async_create_task(self.async_start_websocket())
        
        try:
            data = await self.hass.async_add_executor_job(
                lambda: self._iqua_softener.get_data()
            )
            
            if data is None:
                _LOGGER.error("API returned None data - sensors will show as unknown")
                raise UpdateFailed("API returned no data")
            
            # Log timezone information for debugging
            if hasattr(data, 'device_date_time') and data.device_date_time:
                device_tz = data.device_date_time.tzinfo
                local_time = dt_util.as_local(data.device_date_time)
                _LOGGER.debug("Device time: %s (%s) -> Local: %s (%s)", 
                            data.device_date_time, device_tz, 
                            local_time, local_time.tzinfo)
            
            _LOGGER.info("✅ API refresh completed successfully")
            return data
            
        except TypeError as err:
            # Handle library authentication issues
            if "'str' object is not callable" in str(err):
                _LOGGER.error("iQua library authentication error during API fetch: %s", err)
                # Try to recreate the iqua client to reset authentication state
                try:
                    _LOGGER.info("Attempting to recreate iQua client to reset authentication")
                    from .vendor.iqua_softener import IquaSoftener

                    self._iqua_softener = IquaSoftener(
                        self._username,
                        self._password,
                        device_serial_number=self._device_serial_number,
                        product_serial_number=self._product_serial_number,
                    )
                    # Try the request again with fresh client
                    data = await self.hass.async_add_executor_job(
                        lambda: self._iqua_softener.get_data()
                    )
                    
                    if data is None:
                        _LOGGER.error("API recovery returned None data")
                        raise UpdateFailed("API recovery returned no data")
                    
                    _LOGGER.info("✅ API recovery successful")

                    # Also restart WebSocket with fresh client if enabled
                    if self._enable_websocket:
                        self.hass.async_create_task(self.async_restart_websocket())

                    return data
                except Exception as recovery_err:
                    _LOGGER.error("Failed to recover from authentication error: %s", recovery_err)
                    raise UpdateFailed(f"iQua library authentication error: {err}")
            else:
                _LOGGER.error("Unexpected TypeError in iQua API call: %s", err)
                raise UpdateFailed(f"Unexpected error: {err}")
        except IquaSoftenerException as err:
            _LOGGER.error("API data fetch failed: %s", err)
            raise UpdateFailed(f"Get data failed: {err}")
        except Exception as err:
            _LOGGER.error("Unexpected error fetching API data: %s", err)
            raise UpdateFailed(f"Unexpected error: {err}")


class IquaSoftenerSensor(SensorEntity, CoordinatorEntity, ABC):
    def __init__(
        self,
        coordinator: IquaSoftenerCoordinator,
        device_serial_number: str,
        entity_description: SensorEntityDescription = None,
    ):
        super().__init__(coordinator)
        self._device_serial_number = device_serial_number
        self._attr_unique_id = (
            f"{device_serial_number}_{entity_description.key}".lower()
        )

        if entity_description is not None:
            self.entity_description = entity_description

    @callback
    def _handle_coordinator_update(self) -> None:
        try:
            if self.coordinator.data is None:
                _LOGGER.warning("%s: No data available from coordinator", self.entity_description.name)
                return
                
            self.update(self.coordinator.data)
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Error updating %s sensor: %s", self.entity_description.name, err)

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._device_serial_number)},
            "name": f"Iqua Softener {self._device_serial_number}",
            "manufacturer": "Iqua",
            "model": "Water Softener",
        }

    @abstractmethod
    def update(self, data: IquaSoftenerData): ...


class IquaSoftenerStateSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        try:
            old_value = getattr(self, '_attr_native_value', None)
            self._attr_native_value = str(data.state.value)
            
            if old_value != self._attr_native_value:
                _LOGGER.debug("State changed: %s → %s", old_value, self._attr_native_value)
        except Exception as err:
            _LOGGER.error("Error updating state sensor: %s", err)
            if not hasattr(self, '_attr_native_value'):
                self._attr_native_value = "Unknown"


class IquaSoftenerDeviceDateTimeSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        try:
            # Convert UTC device time to Home Assistant's local timezone
            device_time_local = dt_util.as_local(data.device_date_time)
            # Remove microseconds for cleaner display
            device_time_clean = device_time_local.replace(microsecond=0)
            self._attr_native_value = device_time_clean
            
            # Debug logging for timezone conversion
            _LOGGER.debug("Device time conversion: %s (UTC) -> %s (Local)", 
                         data.device_date_time, device_time_clean)
        except Exception as err:
            _LOGGER.error("Error updating date/time sensor: %s", err)
            if not hasattr(self, '_attr_native_value'):
                self._attr_native_value = None


class IquaSoftenerLastRegenerationSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        try:
            # Calculate last regeneration date in Home Assistant's local timezone
            now_local = dt_util.now()
            last_regen = now_local - timedelta(days=data.days_since_last_regeneration)
            # Set to midnight of that day
            self._attr_native_value = last_regen.replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception as err:
            _LOGGER.error("Error updating last regeneration sensor: %s", err)
            if not hasattr(self, '_attr_native_value'):
                self._attr_native_value = None


class IquaSoftenerOutOfSaltEstimatedDaySensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        try:
            # Calculate out of salt date in Home Assistant's local timezone
            now_local = dt_util.now()
            out_of_salt_date = now_local + timedelta(days=data.out_of_salt_estimated_days)
            # Set to midnight of that day
            self._attr_native_value = out_of_salt_date.replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception as err:
            _LOGGER.error("Error updating out of salt estimation sensor: %s", err)
            if not hasattr(self, '_attr_native_value'):
                self._attr_native_value = None


class IquaSoftenerSaltLevelSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        try:
            old_value = getattr(self, '_attr_native_value', None)
            self._attr_native_value = data.salt_level_percent
            
            if old_value != self._attr_native_value:
                _LOGGER.debug("Salt level changed: %s%% → %s%%", old_value, self._attr_native_value)
        except Exception as err:
            _LOGGER.error("Error updating salt level sensor: %s", err)
            if not hasattr(self, '_attr_native_value'):
                self._attr_native_value = None

    @property
    def icon(self) -> Optional[str]:
        if self._attr_native_value is not None:
            if self._attr_native_value > 75:
                return "mdi:signal-cellular-3"
            elif self._attr_native_value > 50:
                return "mdi:signal-cellular-2"
            elif self._attr_native_value > 25:
                return "mdi:signal-cellular-1"
            elif self._attr_native_value > 5:
                return "mdi:signal-cellular-outline"
            return "mdi:signal-off"
        else:
            return "mdi:signal"


class IquaSoftenerAvailableWaterSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        try:
            self._attr_native_value = data.total_water_available / (
                1000 if data.volume_unit == IquaSoftenerVolumeUnit.LITERS else 1
            )
            self._attr_native_unit_of_measurement = (
                UnitOfVolume.CUBIC_METERS
                if data.volume_unit == IquaSoftenerVolumeUnit.LITERS
                else UnitOfVolume.GALLONS
            )
            # Set last reset to last regeneration in local timezone
            now_local = dt_util.now()
            last_regen = now_local - timedelta(days=data.days_since_last_regeneration)
            self._attr_last_reset = last_regen.replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception as err:
            _LOGGER.error("Error updating available water sensor: %s", err)
            if not hasattr(self, '_attr_native_value'):
                self._attr_native_value = 0


class IquaSoftenerWaterCurrentFlowSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        try:
            # Use the library's get_realtime_property method for real-time flow data
            realtime_flow = self.coordinator._iqua_softener.get_realtime_property(
                "current_water_flow_gpm"
            )
            
            old_value = getattr(self, '_attr_native_value', None)
            
            if realtime_flow is not None:
                # Use real-time WebSocket data
                self._attr_native_value = realtime_flow
                if old_value != self._attr_native_value:
                    _LOGGER.debug("Water flow updated from WebSocket: %s", realtime_flow)
            else:
                # Fall back to regular API data
                self._attr_native_value = data.current_water_flow
                if old_value != self._attr_native_value:
                    _LOGGER.debug("Water flow updated from API: %s", self._attr_native_value)

            self._attr_native_unit_of_measurement = (
                VOLUME_FLOW_RATE_LITERS_PER_MINUTE
                if data.volume_unit == IquaSoftenerVolumeUnit.LITERS
                else VOLUME_FLOW_RATE_GALLONS_PER_MINUTE
            )
        except Exception as err:
            _LOGGER.error("Error updating water flow sensor: %s", err)
            if not hasattr(self, '_attr_native_value'):
                self._attr_native_value = 0


class IquaSoftenerWaterUsageTodaySensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        try:
            old_value = getattr(self, '_attr_native_value', None)
            self._attr_native_value = data.today_use / (
                1000 if data.volume_unit == IquaSoftenerVolumeUnit.LITERS else 1
            )
            self._attr_native_unit_of_measurement = (
                UnitOfVolume.CUBIC_METERS
                if data.volume_unit == IquaSoftenerVolumeUnit.LITERS
                else UnitOfVolume.GALLONS
            )
            
            if old_value != self._attr_native_value:
                _LOGGER.debug("Today's water usage changed: %s → %s %s", 
                            old_value, self._attr_native_value, self._attr_native_unit_of_measurement)
        except Exception as err:
            _LOGGER.error("Error updating today's water usage sensor: %s", err)
            if not hasattr(self, '_attr_native_value'):
                self._attr_native_value = 0


class IquaSoftenerWaterUsageDailyAverageSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        try:
            self._attr_native_value = data.average_daily_use / (
                1000 if data.volume_unit == IquaSoftenerVolumeUnit.LITERS else 1
            )
            self._attr_native_unit_of_measurement = (
                UnitOfVolume.CUBIC_METERS
                if data.volume_unit == IquaSoftenerVolumeUnit.LITERS
                else UnitOfVolume.GALLONS
            )
        except Exception as err:
            _LOGGER.error("Error updating daily average water usage sensor: %s", err)
            if not hasattr(self, '_attr_native_value'):
                self._attr_native_value = 0


class IquaSoftenerWaterShutoffValveStateSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        try:
            if hasattr(data, "water_shutoff_valve_state"):
                # Convert numeric state to text
                valve_state = data.water_shutoff_valve_state
                if valve_state == 1:
                    self._attr_native_value = "Open"
                elif valve_state == 0:
                    self._attr_native_value = "Closed"
                else:
                    self._attr_native_value = f"Unknown ({valve_state})"
            else:
                self._attr_native_value = "Unknown"
        except Exception as err:
            _LOGGER.error("Error updating water shutoff valve sensor: %s", err)
            if not hasattr(self, '_attr_native_value'):
                self._attr_native_value = "Unknown"

    @property
    def icon(self) -> Optional[str]:
        if self._attr_native_value == "Open":
            return "mdi:valve-open"
        elif self._attr_native_value == "Closed":
            return "mdi:valve-closed"
        else:
            return "mdi:valve"