from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import logging
from typing import Optional, Any
import asyncio
import aiohttp
import json
import time

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
    CoordinatorEntity,
)

from iqua_softener import (
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
    DEFAULT_UPDATE_INTERVAL,
    VOLUME_FLOW_RATE_LITERS_PER_MINUTE,
    VOLUME_FLOW_RATE_GALLONS_PER_MINUTE,
    IQUA_WEBSOCKET_BASE_URL,
    CONF_WEBSOCKET_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    config = hass.data[DOMAIN][config_entry.entry_id]
    if config_entry.options:
        config.update(config_entry.options)
    device_serial_number = config[CONF_DEVICE_SERIAL_NUMBER]

    # Use the shared coordinator from __init__.py
    coordinator = config["coordinator"]
    await coordinator.async_config_entry_first_refresh()

    sensors = [
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
            (
                IquaSoftenerWaterShutoffValveStateSensor,
                SensorEntityDescription(
                    key="WATER_SHUTOFF_VALVE_STATE",
                    name="Water shutoff valve state",
                    icon="mdi:valve",
                ),
            ),
        )
    ]
    async_add_entities(sensors)


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
        
        # Home Assistant managed WebSocket
        self._websocket_task = None
        self._websocket_session = None
        self._websocket_uri = None
        self._websocket_failed_permanently = False
        self._last_websocket_refresh = None
        self._websocket_refresh_interval = 3600  # Refresh URI every hour
        self._realtime_data = {}  # Store real-time WebSocket data
        self._realtime_data_timestamps = {}  # Track when real-time data was last updated
        self._realtime_data_timeout = 300  # Clear real-time data after 5 minutes of no updates
        
        # Create a unique WebSocket identifier based on device serial and account
        self._websocket_key = f"iqua_{self._iqua_softener.device_serial_number}_{hash(self._iqua_softener._username)}"
        
        _LOGGER.info(
            "IquaSoftenerCoordinator initialized with %d minute update interval, WebSocket: %s (key: %s)",
            update_interval_minutes,
            enable_websocket,
            self._websocket_key,
        )

    async def async_start_websocket(self):
        """Start the WebSocket connection managed by Home Assistant."""
        if not self._enable_websocket:
            _LOGGER.info("WebSocket disabled, skipping connection")
            return
            
        if self._websocket_failed_permanently:
            _LOGGER.info("WebSocket failed permanently, skipping reconnection attempt")
            return

        # Check if another instance already has a WebSocket for this device
        if 'iqua_websockets' in self.hass.data:
            existing_ws = self.hass.data['iqua_websockets'].get(self._websocket_key)
            if existing_ws and not existing_ws.done():
                _LOGGER.info("WebSocket already active for this device, sharing connection")
                self._websocket_task = existing_ws
                return

        try:
            # Get fresh WebSocket URI from the library
            _LOGGER.info("Getting WebSocket URI from library...")
            self._websocket_uri = await self.hass.async_add_executor_job(
                self._iqua_softener.get_websocket_uri
            )
            
            if not self._websocket_uri:
                _LOGGER.error("WebSocket URI is empty or None")
                return

            # Start the WebSocket task managed by Home Assistant
            _LOGGER.info("Creating Home Assistant managed WebSocket task...")
            self._websocket_task = self.hass.async_create_task(
                self._websocket_handler()
            )
            
            # Store the WebSocket task globally to prevent duplicates
            if 'iqua_websockets' not in self.hass.data:
                self.hass.data['iqua_websockets'] = {}
            self.hass.data['iqua_websockets'][self._websocket_key] = self._websocket_task
            
            _LOGGER.info("Home Assistant WebSocket task created successfully")
        except Exception as err:
            _LOGGER.error("Failed to start WebSocket connection: %s", err)

    async def async_stop_websocket(self):
        """Stop the WebSocket connection."""
        if self._websocket_task:
            self._websocket_task.cancel()
            try:
                await self._websocket_task
            except asyncio.CancelledError:
                pass
            self._websocket_task = None

        if self._websocket_session:
            await self._websocket_session.close()
            self._websocket_session = None

        # Remove from global WebSocket registry
        if 'iqua_websockets' in self.hass.data:
            self.hass.data['iqua_websockets'].pop(self._websocket_key, None)

        # Clear real-time data when WebSocket stops
        self._realtime_data.clear()
        _LOGGER.info("WebSocket connection stopped and real-time data cleared")

    async def _websocket_handler(self):
        """Handle WebSocket connection managed by Home Assistant."""
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                if not self._websocket_session:
                    self._websocket_session = aiohttp.ClientSession()

                _LOGGER.info("Attempting WebSocket connection (attempt %d/%d)", 
                            retry_count + 1, max_retries)

                async with self._websocket_session.ws_connect(
                    self._websocket_uri,
                    timeout=aiohttp.ClientTimeout(total=30),
                    heartbeat=30,
                ) as ws:
                    _LOGGER.info("WebSocket connected successfully")
                    retry_count = 0
                    
                    # Set up periodic URI refresh
                    last_refresh_check = time.time()
                    refresh_check_interval = 1800  # Check every 30 minutes

                    async for msg in ws:
                        # Check if we need to refresh URI periodically
                        current_time = time.time()
                        if current_time - last_refresh_check > refresh_check_interval:
                            _LOGGER.debug("Checking if WebSocket URI needs refresh...")
                            await self._refresh_websocket_uri()
                            last_refresh_check = current_time
                        
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                _LOGGER.debug("Received WebSocket data: %s", data)
                                await self._handle_realtime_data(data)
                            except json.JSONDecodeError as err:
                                _LOGGER.warning("Invalid JSON received: %s", err)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            _LOGGER.error("WebSocket error: %s", ws.exception())
                            break
                        elif msg.type == aiohttp.WSMsgType.CLOSE:
                            _LOGGER.info("WebSocket closed by server")
                            break

            except asyncio.CancelledError:
                _LOGGER.info("WebSocket handler cancelled")
                break
            except aiohttp.ClientResponseError as err:
                if err.status == 400:
                    _LOGGER.error("WebSocket 400 error - likely token expiration: %s", err)
                    if retry_count < max_retries - 1:
                        _LOGGER.info("Attempting to refresh WebSocket URI due to 400 error...")
                        try:
                            await self._refresh_websocket_uri()
                            if self._websocket_uri:
                                _LOGGER.info("WebSocket URI refreshed successfully, will retry connection")
                            else:
                                _LOGGER.error("WebSocket URI refresh failed")
                        except Exception as refresh_err:
                            _LOGGER.error("Failed to refresh WebSocket URI: %s", refresh_err)
                else:
                    _LOGGER.error("WebSocket HTTP error (attempt %d/%d): %s", 
                                 retry_count + 1, max_retries, err)
            except Exception as err:
                _LOGGER.error("WebSocket connection error (attempt %d/%d): %s", 
                             retry_count + 1, max_retries, err)

            retry_count += 1
            if retry_count < max_retries:
                wait_time = min(60 * retry_count, 300)
                _LOGGER.info("Waiting %d seconds before retry...", wait_time)
                await asyncio.sleep(wait_time)
            else:
                _LOGGER.error("Max WebSocket retry attempts reached. WebSocket functionality disabled.")
                self._websocket_failed_permanently = True
                break

    async def _refresh_websocket_uri(self):
        """Refresh the WebSocket URI using the library."""
        try:
            current_time = time.time()
            
            # Check if we need to refresh based on time
            if (self._last_websocket_refresh and 
                current_time - self._last_websocket_refresh < self._websocket_refresh_interval):
                time_since_refresh = current_time - self._last_websocket_refresh
                _LOGGER.debug("WebSocket URI was refreshed %.0f seconds ago, skipping refresh", time_since_refresh)
                return
            
            _LOGGER.info("Refreshing WebSocket URI using library...")
            new_uri = await self.hass.async_add_executor_job(
                self._iqua_softener.get_websocket_uri
            )
            
            if new_uri and new_uri != self._websocket_uri:
                self._websocket_uri = new_uri
                self._last_websocket_refresh = current_time
                _LOGGER.info("WebSocket URI refreshed successfully")
            else:
                _LOGGER.error("WebSocket URI refresh returned empty/None or same URI")
                
        except Exception as err:
            _LOGGER.error("Failed to refresh WebSocket URI: %s", err)

    async def _handle_realtime_data(self, data):
        """Handle real-time data updates from WebSocket."""
        try:
            _LOGGER.debug("Processing real-time data: %s", data)
            
            # Handle current_water_flow_gpm specifically
            if isinstance(data, dict) and data.get("name") == "current_water_flow_gpm":
                if "converted_property" in data and "value" in data["converted_property"]:
                    corrected_flow_value = data["converted_property"]["value"]
                    original_value = data.get("value", "unknown")
                    
                    _LOGGER.info(
                        "WebSocket water flow update: raw=%s -> converted=%s gpm",
                        original_value,
                        corrected_flow_value,
                    )
                    
                    # Store the corrected value and update the library
                    self._realtime_data["current_water_flow_gpm"] = corrected_flow_value
                    self._realtime_data_timestamps["current_water_flow_gpm"] = time.time()
                    
                    # Update the library's external real-time data
                    await self.hass.async_add_executor_job(
                        self._iqua_softener.update_external_realtime_data, {data["name"]: data}
                    )

            # Trigger coordinator update to refresh all entities
            await self.async_request_refresh()
            _LOGGER.debug("Real-time data processed successfully")
        except Exception as err:
            _LOGGER.error("Failed to handle real-time data: %s", err)

    async def async_retry_websocket(self):
        """Manually retry WebSocket connection."""
        _LOGGER.info("Manual WebSocket retry requested")
        self._websocket_failed_permanently = False
        await self.async_stop_websocket()
        await self.async_start_websocket()

    async def _async_update_data(self) -> IquaSoftenerData:
        _LOGGER.debug("Fetching data from iQua API")
        try:
            data = await self.hass.async_add_executor_job(
                lambda: self._iqua_softener.get_data()
            )
            _LOGGER.debug("Successfully fetched data from iQua API")
            return data
        except IquaSoftenerException as err:
            _LOGGER.error("Get data failed: %s", err)
            raise UpdateFailed(f"Get data failed: {err}")


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
        self.update(self.coordinator.data)
        self.async_write_ha_state()

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
        self._attr_native_value = str(data.state.value)


class IquaSoftenerDeviceDateTimeSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        self._attr_native_value = data.device_date_time.strftime("%Y-%m-%d %H:%M:%S")


class IquaSoftenerLastRegenerationSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        self._attr_native_value = (
            datetime.now(data.device_date_time.tzinfo)
            - timedelta(days=data.days_since_last_regeneration)
        ).replace(hour=0, minute=0, second=0)


class IquaSoftenerOutOfSaltEstimatedDaySensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        self._attr_native_value = (
            datetime.now(data.device_date_time.tzinfo)
            + timedelta(days=data.out_of_salt_estimated_days)
        ).replace(hour=0, minute=0, second=0)


class IquaSoftenerSaltLevelSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        self._attr_native_value = data.salt_level_percent

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
        self._attr_native_value = data.total_water_available / (
            1000 if data.volume_unit == IquaSoftenerVolumeUnit.LITERS else 1
        )
        self._attr_native_unit_of_measurement = (
            UnitOfVolume.CUBIC_METERS
            if data.volume_unit == IquaSoftenerVolumeUnit.LITERS
            else UnitOfVolume.GALLONS
        )
        self._attr_last_reset = datetime.now(data.device_date_time.tzinfo) - timedelta(
            days=data.days_since_last_regeneration
        )


class IquaSoftenerWaterCurrentFlowSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        # Use the library's get_realtime_property method for real-time flow data
        realtime_flow = self.coordinator._iqua_softener.get_realtime_property("current_water_flow_gpm")
        
        if realtime_flow is not None:
            # Use real-time WebSocket data
            self._attr_native_value = realtime_flow
            _LOGGER.debug("Using real-time water flow from library: %s", realtime_flow)
        else:
            # Fall back to regular API data
            self._attr_native_value = data.current_water_flow
            _LOGGER.debug("Using API water flow: %s", self._attr_native_value)
            
        self._attr_native_unit_of_measurement = (
            VOLUME_FLOW_RATE_LITERS_PER_MINUTE
            if data.volume_unit == IquaSoftenerVolumeUnit.LITERS
            else VOLUME_FLOW_RATE_GALLONS_PER_MINUTE
        )


class IquaSoftenerWaterUsageTodaySensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        self._attr_native_value = data.today_use / (
            1000 if data.volume_unit == IquaSoftenerVolumeUnit.LITERS else 1
        )
        self._attr_native_unit_of_measurement = (
            UnitOfVolume.CUBIC_METERS
            if data.volume_unit == IquaSoftenerVolumeUnit.LITERS
            else UnitOfVolume.GALLONS
        )


class IquaSoftenerWaterUsageDailyAverageSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
        self._attr_native_value = data.average_daily_use / (
            1000 if data.volume_unit == IquaSoftenerVolumeUnit.LITERS else 1
        )
        self._attr_native_unit_of_measurement = (
            UnitOfVolume.CUBIC_METERS
            if data.volume_unit == IquaSoftenerVolumeUnit.LITERS
            else UnitOfVolume.GALLONS
        )


class IquaSoftenerWaterShutoffValveStateSensor(IquaSoftenerSensor):
    def update(self, data: IquaSoftenerData):
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

    @property
    def icon(self) -> Optional[str]:
        if self._attr_native_value == "Open":
            return "mdi:valve-open"
        elif self._attr_native_value == "Closed":
            return "mdi:valve-closed"
        else:
            return "mdi:valve"
