import logging
import time
import json
import os
import threading
import asyncio
from enum import Enum, IntEnum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, Callable

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

import requests

try:
    import jwt  # optional (PyJWT)
except ImportError:
    jwt = None

try:
    import websockets
except ImportError:
    websockets = None

logger = logging.getLogger(__name__)


DEFAULT_API_BASE_URL = "https://api.myiquaapp.com/v1"


class IquaSoftenerState(str, Enum):
    ONLINE = "Online"
    OFFLINE = "Offline"


class IquaSoftenerVolumeUnit(IntEnum):
    GALLONS = 0
    LITERS = 1


class IquaSoftenerException(Exception):
    pass


@dataclass(frozen=True)
class IquaSoftenerData:
    timestamp: datetime
    model: str
    state: IquaSoftenerState
    device_date_time: datetime
    volume_unit: IquaSoftenerVolumeUnit
    current_water_flow: float
    today_use: int
    average_daily_use: int
    total_water_available: int
    days_since_last_regeneration: int
    salt_level: int
    salt_level_percent: int
    out_of_salt_estimated_days: int
    hardness_grains: int
    water_shutoff_valve_state: int


class IquaSoftener:
    def __init__(
        self,
        username: str,
        password: str,
        device_serial_number: Optional[str] = None,
        product_serial_number: Optional[str] = None,
        api_base_url: str = DEFAULT_API_BASE_URL,
        enable_websocket: bool = True,
        external_realtime_data: Optional[Dict[str, Any]] = None,
    ):
        self._username: str = username
        self._password: str = password
        self._device_serial_number = device_serial_number
        self._product_serial_number = product_serial_number
        self._api_base_url: str = api_base_url
        
        # Validate that at least one serial number is provided
        if not device_serial_number and not product_serial_number:
            raise ValueError("Either device_serial_number or product_serial_number must be provided")
        self._session: Optional[requests.Session] = None
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._user_id: Optional[str] = None
        self._access_expires_at: Optional[int] = None
        self._device_id: Optional[str] = None  # Cache the device ID

        # WebSocket support
        self._enable_websocket = enable_websocket and websockets is not None
        self._websocket_uri: Optional[str] = None
        self._websocket_task: Optional[asyncio.Task] = None
        self._websocket_thread: Optional[threading.Thread] = None
        self._websocket_loop: Optional[asyncio.AbstractEventLoop] = None
        self._realtime_data: Dict[str, Any] = {}
        self._websocket_running = False
        self._websocket_lock = threading.Lock()
        self._websocket_connected_at: Optional[float] = None
        self._websocket_max_duration = 170  # Reconnect after 170 seconds (before 3 min timeout)

        # External real-time data (for Home Assistant integration)
        self._external_realtime_data = external_realtime_data

    @property
    def device_serial_number(self) -> Optional[str]:
        return self._device_serial_number
    
    @property
    def product_serial_number(self) -> Optional[str]:
        return self._product_serial_number

    def get_data(self) -> IquaSoftenerData:
        device_id = self._get_device_id()
        device = self._get_device_detail(device_id)
        props = device.get("properties", {})
        enriched = device.get("enriched_data", {}).get("water_treatment", {})

        def val(name: str, default=None):
            return props.get(name, {}).get("value", default)

        def enriched_val(name: str, default=None):
            """Get value from enriched_data."""
            return enriched.get(name, default)

        def realtime_val(name: str, fallback_name: str = None, default=None):
            """Get value from real-time data if available, otherwise fallback to API data."""
            realtime_value = self.get_realtime_property(name)
            if realtime_value is not None:
                return realtime_value
            if fallback_name:
                return val(fallback_name, default)
            return val(name, default)

        model_desc = val("model_description", "Unknown Model")
        model_id = val("model_id", "N/A")

        # Get device date from properties or use current time
        device_date_str = val("device_date")
        if device_date_str:
            try:
                # Parse the device date, assuming it's in ISO format
                device_date_time = datetime.fromisoformat(
                    device_date_str.rstrip("Z")
                ).replace(tzinfo=ZoneInfo("UTC"))
            except (ValueError, AttributeError):
                device_date_time = datetime.now(tz=ZoneInfo("UTC"))
        else:
            device_date_time = datetime.now(tz=ZoneInfo("UTC"))

        # Use real-time service_active if available
        service_active = realtime_val("service_active", "service_active", True)

        return IquaSoftenerData(
            timestamp=datetime.now(tz=ZoneInfo("UTC")),
            model=f"{model_desc} ({model_id})",
            state=(
                IquaSoftenerState.ONLINE
                if service_active
                else IquaSoftenerState.OFFLINE
            ),
            device_date_time=device_date_time,
            volume_unit=IquaSoftenerVolumeUnit(int(val("volume_unit_enum", 0))),
            # Use real-time current_water_flow if available
            current_water_flow=float(
                realtime_val("current_water_flow_gpm")
                or props.get("current_water_flow_gpm", {}).get("converted_value", 0.0)
            ),
            # Use enriched_data for today's usage if available
            today_use=int(
                enriched_val("gallons_used_today") or val("gallons_used_today", 0)
            ),
            average_daily_use=int(val("avg_daily_use_gals", 0)),
            # Use enriched_data for treated water available
            total_water_available=int(
                enriched_val("treated_water_available", {}).get("value")
                or val("treated_water_avail_gals", 0)
            ),
            # Use enriched_data for days since last regeneration
            days_since_last_regeneration=int(
                enriched_val("days_since_last_recharge")
                or val("days_since_last_regen", 0)
            ),
            salt_level=int(val("salt_level_tenths", 0) / 10),
            # Use enriched_data for salt level percent
            salt_level_percent=int(enriched_val("salt_level_percent") or 0),
            out_of_salt_estimated_days=int(val("out_of_salt_estimate_days", 0)),
            hardness_grains=int(val("hardness_grains", 0)),
            water_shutoff_valve_state=self._get_water_shutoff_valve_state(device),
        )

    def get_flow_and_salt(self) -> dict:
        """Return just flow (gpm) and salt level percent for quick dashboards."""
        # Try to get real-time flow first
        realtime_flow = self.get_realtime_property("current_water_flow_gpm")

        if realtime_flow is not None:
            flow = realtime_flow
        else:
            # Fallback to API data
            device_id = self._get_device_id()
            device = self._get_device_detail(device_id)
            props = device.get("properties", {})
            flow = props.get("current_water_flow_gpm", {}).get("converted_value", 0.0)

        # Salt level is typically not real-time, so get from API
        device_id = self._get_device_id()
        device = self._get_device_detail(device_id)
        salt = (
            device.get("enriched_data", {})
            .get("water_treatment", {})
            .get("salt_level_percent")
        )

        return {"flow_gpm": flow, "salt_percent": salt}

    def set_water_shutoff_valve(self, state: int):
        if state not in (0, 1):
            raise ValueError(
                "Invalid state for water shutoff valve (should be 0 or 1)."
            )

        device_id = self._get_device_id()
        url = f"/devices/{device_id}/command"

        # Convert state to action string: 1 = open, 0 = closed
        action = "open" if state == 1 else "close"
        payload = {"function": "water_shutoff_valve", "action": action}

        response = self._request("PUT", url, json=payload)
        if response.status_code != 200:
            raise IquaSoftenerException(
                f"Invalid status ({response.status_code}) for set water shutoff valve request"
            )
        response_data = response.json()
        return response_data

    def open_water_shutoff_valve(self):
        """Open the water shutoff valve (allow water flow) - state 1."""
        return self.set_water_shutoff_valve(1)

    def close_water_shutoff_valve(self):
        """Close the water shutoff valve (stop water flow) - state 0."""
        return self.set_water_shutoff_valve(0)

    def schedule_regeneration(self):
        """Schedule a regeneration cycle for the water softener."""
        device_id = self._get_device_id()
        url = f"/devices/{device_id}/command"
        payload = {"function": "regenerate", "action": "schedule"}

        response = self._request("PUT", url, json=payload)
        if response.status_code != 200:
            raise IquaSoftenerException(
                f"Invalid status ({response.status_code}) for schedule regeneration request"
            )
        response_data = response.json()
        return response_data

    def cancel_scheduled_regeneration(self):
        """Cancel a scheduled regeneration cycle."""
        device_id = self._get_device_id()
        url = f"/devices/{device_id}/command"
        payload = {"function": "regenerate", "action": "cancel"}

        response = self._request("PUT", url, json=payload)
        if response.status_code != 200:
            raise IquaSoftenerException(
                f"Invalid status ({response.status_code}) for cancel regeneration request"
            )
        response_data = response.json()
        return response_data

    def regenerate_now(self):
        """Start a regeneration cycle immediately."""
        device_id = self._get_device_id()
        url = f"/devices/{device_id}/command"
        payload = {"function": "regenerate", "action": "regenerate"}

        response = self._request("PUT", url, json=payload)
        if response.status_code != 200:
            raise IquaSoftenerException(
                f"Invalid status ({response.status_code}) for regenerate now request"
            )
        response_data = response.json()
        return response_data

    def get_devices(self) -> list:
        """Get list of all devices for the authenticated user."""
        return self._get_devices()

    def get_device_id(self) -> str:
        """Get the device ID for the configured serial number."""
        return self._get_device_id()

    def get_device_details(self) -> dict:
        """Get detailed device information for the configured device."""
        device_id = self._get_device_id()
        return self._get_device_detail(device_id)

    def has_water_shutoff_valve(self) -> bool:
        """Check if the device has a water shutoff valve installed."""
        try:
            device_id = self._get_device_id()
            device = self._get_device_detail(device_id)
            
            # Check for water_shutoff_valve in multiple locations
            valve_data = None
            
            # Check enriched_data first
            enriched = device.get("enriched_data", {}).get("water_treatment", {})
            valve_data = enriched.get("water_shutoff_valve", {})
            
            # If not in enriched_data, check properties
            if not valve_data:
                props = device.get("properties", {})
                valve_data = props.get("water_shutoff_valve", {})
            
            # If still not found, check device root level  
            if not valve_data:
                valve_data = device.get("water_shutoff_valve", {})
            
            # Check if valve is installed
            if isinstance(valve_data, dict):
                return valve_data.get("is_installed", False)
            
            return False
        except Exception as e:
            logger.error(f"Error checking water shutoff valve availability: {e}")
            return False

    def start_websocket(self):
        """Start WebSocket connection for real-time updates."""
        if not self._enable_websocket:
            logger.warning(
                "WebSocket support is disabled or websockets library not available"
            )
            return

        if self._websocket_running:
            logger.info("WebSocket already running")
            return

        self._websocket_running = True
        self._websocket_thread = threading.Thread(
            target=self._run_websocket_thread, daemon=True
        )
        self._websocket_thread.start()

    def stop_websocket(self):
        """Stop WebSocket connection."""
        if not self._websocket_running:
            return

        self._websocket_running = False

        if self._websocket_loop and self._websocket_task:
            self._websocket_loop.call_soon_threadsafe(self._websocket_task.cancel)

        if self._websocket_thread:
            self._websocket_thread.join(timeout=5)

    def get_realtime_property(self, property_name: str) -> Optional[Any]:
        """Get a real-time property value from WebSocket data."""
        # Check external real-time data first (for Home Assistant integration)
        if self._external_realtime_data:
            prop_data = self._external_realtime_data.get(property_name)
            if prop_data:
                if prop_data.get("converted_property"):
                    return prop_data["converted_property"]["value"]
                return prop_data.get("value")

        # Fall back to internal WebSocket data
        with self._websocket_lock:
            prop_data = self._realtime_data.get(property_name)
            if prop_data:
                # Return converted_value if available, otherwise raw value
                if prop_data.get("converted_property"):
                    return prop_data["converted_property"]["value"]
                return prop_data.get("value")
            return None

    def update_external_realtime_data(self, realtime_data: Dict[str, Any]):
        """Update external real-time data (for Home Assistant integration)."""
        self._external_realtime_data = realtime_data

    def get_websocket_uri(self) -> Optional[str]:
        """Get WebSocket URI for external use (like Home Assistant integration)."""
        try:
            device_id = self._get_device_id()
            response = self._request("GET", f"/devices/{device_id}/live")
            data = response.json()
            ws_uri = data.get("websocket_uri")
            if ws_uri:
                return f"wss://api.myiquaapp.com{ws_uri}"
            return None
        except Exception as e:
            logger.error(f"Failed to get WebSocket URI: {e}")
            return None

    def _run_websocket_thread(self):
        """Run WebSocket client in a separate thread."""
        try:
            self._websocket_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._websocket_loop)
            self._websocket_loop.run_until_complete(self._websocket_client())
        except Exception as e:
            logger.error(f"WebSocket thread error: {e}")
        finally:
            if self._websocket_loop:
                self._websocket_loop.close()

    async def _websocket_client(self):
        """WebSocket client coroutine."""
        while self._websocket_running:
            try:
                # Get WebSocket URI
                ws_uri = await self._get_websocket_uri()
                if not ws_uri:
                    await asyncio.sleep(30)
                    continue

                full_uri = f"wss://api.myiquaapp.com{ws_uri}"
                logger.info(f"Connecting to WebSocket: {full_uri}")

                async with websockets.connect(full_uri) as websocket:
                    logger.info("WebSocket connected successfully")
                    self._websocket_task = asyncio.current_task()
                    self._websocket_connected_at = time.time()

                    async for message in websocket:
                        if not self._websocket_running:
                            break

                        # Check if we've been connected too long (proactive reconnect)
                        if self._websocket_connected_at:
                            connection_duration = time.time() - self._websocket_connected_at
                            if connection_duration >= self._websocket_max_duration:
                                logger.info(
                                    f"WebSocket connection duration ({connection_duration:.1f}s) "
                                    f"exceeded max ({self._websocket_max_duration}s), reconnecting..."
                                )
                                break

                        try:
                            data = json.loads(message)
                            await self._handle_websocket_message(data)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse WebSocket message: {e}")
                        except Exception as e:
                            logger.error(f"Error handling WebSocket message: {e}")

            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                self._websocket_connected_at = None
                if self._websocket_running:
                    await asyncio.sleep(10)  # Wait before reconnecting

    async def _get_websocket_uri(self) -> Optional[str]:
        """Get WebSocket URI from the API."""
        try:
            device_id = self._get_device_id()
            response = self._request("GET", f"/devices/{device_id}/live")
            data = response.json()
            return data.get("websocket_uri")
        except Exception as e:
            logger.error(f"Failed to get WebSocket URI: {e}")
            return None

    async def _handle_websocket_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket message."""
        if data.get("type") == "property" and "name" in data:
            property_name = data["name"]
            with self._websocket_lock:
                self._realtime_data[property_name] = data
            logger.debug(
                f"Updated real-time property: {property_name} = {data.get('value')}"
            )

    def save_tokens(self, path: str):
        """Save authentication tokens to a file."""
        with open(path, "w") as f:
            json.dump(
                {
                    "access_token": self._access_token,
                    "refresh_token": self._refresh_token,
                    "user_id": self._user_id,
                    "_access_expires_at": self._access_expires_at,
                },
                f,
            )

    def load_tokens(self, path: str):
        """Load authentication tokens from a file."""
        if not os.path.exists(path):
            return
        with open(path, "r") as f:
            data = json.load(f)
        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        self._user_id = data.get("user_id")
        self._access_expires_at = data.get("_access_expires_at")

    def _get_water_shutoff_valve_state(self, device: dict) -> int:
        """Parse water shutoff valve state from API device data."""
        # Check enriched_data first (this is where it should be)
        enriched = device.get("enriched_data", {}).get("water_treatment", {})
        valve_data = enriched.get("water_shutoff_valve", {})
        # If not in enriched_data, check properties as fallback
        if not valve_data:
            props = device.get("properties", {})
            valve_data = props.get("water_shutoff_valve", {})

        # If still not found, check device root level
        if not valve_data:
            valve_data = device.get("water_shutoff_valve", {})

        if isinstance(valve_data, dict):
            # Check if valve is installed first
            is_installed = valve_data.get("is_installed", False)
            if not is_installed:
                return 0  # Default to closed if not installed
                
            status = valve_data.get("status", "closed")
            # Convert status string to int: "open" = 1, "closed" = 0
            return 1 if status == "open" else 0
        # Fallback for legacy numeric format
        return int(valve_data) if valve_data is not None else 0

    def _get_device_id(self) -> str:
        """Get the device ID for the configured serial number."""
        if self._device_id is not None:
            return self._device_id

        # Get all devices and find the one with matching serial number
        devices = self._get_devices()
        for device in devices:
            props = device.get("properties", {})
            
            # Check device_serial_number field if provided
            if self._device_serial_number:
                device_serial = props.get("serial_number", {}).get("value")
                if device_serial == self._device_serial_number:
                    self._device_id = device["id"]
                    return self._device_id
            
            # Check product_serial_number field if provided
            if self._product_serial_number:
                product_serial = props.get("product_serial_number", {}).get("value")
                if product_serial == self._product_serial_number:
                    self._device_id = device["id"]
                    return self._device_id

        # Build error message based on what was provided
        if self._device_serial_number and self._product_serial_number:
            identifier = f"device serial number '{self._device_serial_number}' or product serial number '{self._product_serial_number}'"
        elif self._device_serial_number:
            identifier = f"device serial number '{self._device_serial_number}'"
        else:
            identifier = f"product serial number '{self._product_serial_number}'"
        
        raise IquaSoftenerException(
            f"Device with {identifier} not found"
        )

    def _get_devices(self) -> list:
        """Get list of all devices for the authenticated user."""
        r = self._request("GET", "/devices")
        data = r.json()
        return data.get("data", [])

    def _ensure_session(self):
        """Ensure we have a session object."""
        if self._session is None:
            self._session = requests.Session()

    def _set_tokens(self, access_token: str, refresh_token: Optional[str]):
        """Set authentication tokens and update session headers."""
        self._access_token = access_token
        self._refresh_token = refresh_token
        if jwt:
            try:
                decoded = jwt.decode(access_token, options={"verify_signature": False})
                exp = decoded.get("exp")
                if exp:
                    self._access_expires_at = int(exp) - 60
            except Exception:
                self._access_expires_at = None

        self._ensure_session()
        if self._access_token:
            self._session.headers.update(
                {"Authorization": f"Bearer {self._access_token}"}
            )

    def _is_token_expired(self) -> bool:
        """Check if the current access token is expired."""
        if not self._access_token:
            return True
        if self._access_expires_at is None:
            return False
        return time.time() >= self._access_expires_at

    def _login(self) -> Dict[str, Any]:
        """Authenticate with the API and get tokens."""
        self._ensure_session()
        url = f"{self._api_base_url}/auth/login"
        payload = {"email": self._username, "password": self._password}
        try:
            r = self._session.post(url, json=payload, timeout=15)
        except requests.exceptions.RequestException as ex:
            raise IquaSoftenerException(f"Exception on login request ({ex})")

        if r.status_code == 401:
            raise IquaSoftenerException(f"Authentication error ({r.text})")
        if r.status_code != 200:
            raise IquaSoftenerException(f"Login failed: {r.status_code} {r.text}")

        data = r.json()
        self._set_tokens(data.get("access_token"), data.get("refresh_token"))
        self._user_id = data.get("user_id")
        return data

    def _refresh_access_token(self) -> Dict[str, Any]:
        """Refresh the access token using the refresh token."""
        if not self._refresh_token:
            raise IquaSoftenerException("No refresh token available")

        self._ensure_session()
        url = f"{self._api_base_url}/auth/refresh"
        payload = {"refresh_token": self._refresh_token}
        try:
            r = self._session.post(url, json=payload, timeout=15)
        except requests.exceptions.RequestException as ex:
            raise IquaSoftenerException(f"Exception on token refresh ({ex})")

        if r.status_code != 200:
            raise IquaSoftenerException(f"Refresh failed: {r.status_code} {r.text}")

        data = r.json()
        self._set_tokens(data.get("access_token"), data.get("refresh_token"))
        return data

    def _ensure_authenticated(self):
        """Ensure we have a valid authentication token."""
        if self._is_token_expired():
            try:
                if self._refresh_token:
                    self._refresh_access_token()
                else:
                    self._login()
            except IquaSoftenerException:
                self._login()

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make an authenticated request to the API."""
        self._ensure_authenticated()
        self._ensure_session()

        url = (
            path
            if path.startswith("http")
            else f"{self._api_base_url.rstrip('/')}/{path.lstrip('/')}"
        )

        r = self._session.request(method, url, timeout=20, **kwargs)
        if r.status_code == 401 and self._refresh_token:
            try:
                self._refresh_access_token()
                r = self._session.request(method, url, timeout=20, **kwargs)
            except IquaSoftenerException:
                self._login()
                r = self._session.request(method, url, timeout=20, **kwargs)

        if r.status_code != 200:
            r.raise_for_status()
        return r

    def _get_device_detail(self, device_id: str) -> dict:
        """Get detailed device information."""
        r = self._request("GET", f"/devices/{device_id}/detail-or-summary")
        data = r.json()
        return data.get("device", {})
