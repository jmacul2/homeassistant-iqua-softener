# Changelog

All notable changes to the iQua Softener Home Assistant integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.2] - 2025-11-09

### Added
- **Conditional Water Shutoff Valve Entities**: Switch and valve state sensor now only appear if the device actually has a water shutoff valve installed
  - Added `has_water_shutoff_valve()` method to library for proper device capability detection
  - Added `get_device_details()` public method for external access to device information
  - Enhanced device detection logic to check `is_installed` field in water shutoff valve data
- **Configuration Flow Validation**: Added real-time credential validation during setup
  - Credentials and device access are now validated before completing the integration setup
  - Users cannot complete setup with invalid credentials or unreachable devices
  - Added progress indicators during validation with user-friendly error messages
  - Added reconfigure flow support for updating credentials

### Fixed
- **Missing Switch Issue**: Fixed water shutoff valve switch not appearing due to product serial number handling
  - Resolved product serial number support in switch platform setup
  - Fixed device serial number extraction to properly handle both device_sn and product_sn configurations
- **Improved Water Shutoff Valve Detection**: Enhanced API parsing to properly detect valve availability
  - Updated valve state parsing to respect `is_installed` field from device API response
  - Added comprehensive valve availability checking across multiple API data locations (enriched_data, properties, root level)
  - Switch and valve state sensor creation now conditional based on actual device capabilities
- **Authentication Error Handling**: Improved startup error handling to prevent platform setup failures
  - Added proper `ConfigEntryNotReady` exception handling for authentication failures
  - Authentication is now validated before setting up sensor and switch platforms
  - Prevents Home Assistant platform errors when credentials are invalid or API is unavailable

### Enhanced
- **Better Error Handling**: Improved logging and error handling for water shutoff valve operations
- **Device Capability Detection**: More robust detection of device features before creating entities
- **API Response Parsing**: Enhanced parsing of device details to handle various API response formats
- **Integration Startup**: Improved startup sequence with proper authentication validation and error reporting
- **User Experience**: Enhanced configuration flow with real-time validation and clear error messages

## [2.0.1] - 2025-11-09

### Added
- **Product Serial Number Support**: Added alternative configuration option to use Product Serial Number instead of Device Serial Number
- **Timezone-Aware Timestamps**: All timestamp sensors now properly convert device UTC time to Home Assistant's local timezone
  - Last regeneration dates now display in local time
  - Out of salt estimated dates now display in local time
  - Available water sensor reset times now use local timezone

### Changed
- Configuration flow now accepts either Device Serial Number OR Product Serial Number (not both required)
- Enhanced validation in configuration flow with clearer error messages
- Improved timezone handling for better compatibility across different Home Assistant installations

### Fixed
- Resolved timezone conversion issues that could cause incorrect date displays
- Fixed configuration validation to properly handle missing serial numbers

## [2.0.0] - 2025-11-01

### Added
- **🔄 Real-time Updates**: Complete WebSocket implementation for instant water flow monitoring
  - Real-time water current flow updates via WebSocket connection
  - Automatic fallback to API polling for other sensors
  - Hybrid approach: real-time for critical data, efficient polling for less time-sensitive data
- **💧 Water Control**: Remote water shutoff valve control capabilities
  - New switch entity for opening/closing water shutoff valve
  - Water shutoff valve state sensor showing current valve position (Open/Closed)
  - Optimistic state updates with configurable timeout
  - Perfect for emergency water shutoff and leak prevention automations
- **📊 Enhanced Sensors**: Comprehensive monitoring with 10+ sensors
  - State sensor (Online/Offline status)
  - Date/time sensor with timezone awareness
  - Last regeneration timestamp
  - Out of salt estimated day
  - Salt level percentage with dynamic icons
  - Available water with proper unit conversion
  - Water current flow with real-time updates
  - Today's water usage tracking
  - Daily average water usage
  - Water shutoff valve state monitoring
- **⚙️ Configurable Options**: Advanced configuration capabilities
  - Adjustable polling intervals (1-60 minutes, default: 5 minutes)
  - Toggle for enabling/disabling real-time WebSocket updates
  - Options flow for runtime configuration changes
- **🏠 Native Home Assistant Integration**: Full platform integration
  - Proper device grouping with device registry
  - Device information with manufacturer and model details
  - Unique entity IDs based on device serial numbers
  - Home Assistant device classes and state classes
- **🔧 Enhanced Library Integration**: Vendored library with improvements
  - Includes vendored `iqua-softener` library with WebSocket enhancements
  - Enhanced authentication and token management
  - Improved error handling and recovery mechanisms
  - No manual library installation required

### Enhanced
- **WebSocket Architecture**: 
  - Automatic URI refresh every 170 seconds (before 3-minute timeout)
  - Robust connection management with automatic reconnection
  - Proper error handling for authentication and network issues
  - Throttled updates to prevent excessive sensor refreshes
- **Authentication System**:
  - Improved JWT token handling and refresh mechanisms
  - Automatic client recreation on authentication errors
  - Better error recovery for API and WebSocket connections
- **Sensor Updates**:
  - Immediate sensor initialization with current data on startup
  - Smart update source tracking (API vs WebSocket)
  - Enhanced error handling with fallback values
  - Improved logging for debugging and monitoring
- **Configuration Flow**:
  - User-friendly setup wizard with validation
  - Clear error messages and help text
  - Support for different serial number types
  - Options flow for post-installation configuration

### Technical Improvements
- **Volume Unit Handling**: Proper support for both Gallons and Liters with automatic conversion
- **Device Classes**: Correct Home Assistant device classes for water sensors
- **State Classes**: Proper state classes for measurement, total, and total_increasing sensors
- **Icon Management**: Dynamic icons based on sensor values (e.g., salt level indicators)
- **Timestamp Handling**: Proper UTC to local timezone conversion for all timestamps
- **Error Recovery**: Robust error handling with automatic recovery mechanisms
- **Memory Management**: Efficient WebSocket connection management to prevent memory leaks

### Dependencies
- Removed external dependency on `iqua-softener` PyPI package
- Added direct dependencies: `requests`, `PyJWT`
- Includes vendored library with all necessary enhancements

### Breaking Changes
- Minimum Home Assistant version: 2023.1.0
- Configuration may need to be updated if using old device serial number format
- Entity unique IDs may change due to improved device identification

---

## Previous Versions

### [1.x] - Legacy
- Basic sensor support for water softener data
- Simple polling-based updates
- Limited device control capabilities

---

## Installation Notes

### Upgrading from 1.x to 2.0.0+
1. **Backup Configuration**: Export your current configuration before upgrading
2. **Remove Old Installation**: Remove any manually installed `iqua-softener` library
3. **Install via HACS**: Use HACS to install the new version
4. **Reconfigure Integration**: You may need to reconfigure the integration with the new options
5. **Update Automations**: Review and update any automations using the old entity names

### New Installation
1. Install via HACS custom repository: `https://github.com/jmacul2/homeassistant-iqua-softener`
2. Restart Home Assistant
3. Add integration via Settings → Devices & Services → Add Integration
4. Search for "iQua Softener" and follow the configuration wizard

For detailed installation and configuration instructions, see the [README.md](README.md).