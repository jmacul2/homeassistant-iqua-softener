# iQua app supported water softeners integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/jmacul2/homeassistant-iqua-softener.svg)](https://github.com/jmacul2/homeassistant-iqua-softener/releases)

`iqua_softener` is a _custom component_ for [Home Assistant](https://www.home-assistant.io/). The integration allows you to pull data for you iQua app supported water softener from Ecowater company server.

## Features

- **🔄 Real-time Updates**: WebSocket support for instant water flow monitoring
- **💧 Water Control**: Remote water shutoff valve control for emergency situations
- **📊 Comprehensive Monitoring**: 10 sensors covering all aspects of your water softener
- **⚙️ Configurable**: Adjustable polling intervals and real-time update settings
- **🏠 Native Integration**: Full Home Assistant integration with device grouping
- **🔧 Automation Ready**: Perfect for leak detection and water usage automations

It will create ten sensors with both periodic updates and real-time WebSocket data (default polling interval: 5 minutes, with real-time flow updates):
- State - whether the softener is connected to Ecowater server
- Date/time - date and time set on water softener
- Last regeneration - the day of last regeneration
- Out of salt estimated day - the day on which the end of salt is predicted
- Salt level - salt level load in percentage
- Today water usage - water used today
- Water current flow - current flow of water
- Water usage daily average - computed average by softener of daily usage
- Available water - water available to use before next regeneration
- Water shutoff valve state - current state of the water shutoff valve (Open/Closed)

It will also create one switch:
- Water shutoff valve - allows you to remotely open/close the water shutoff valve

The units displayed are set in the application settings.

![Homeassistant sensor dialog](sensor.png)

## Real-Time Data Updates

The integration now supports real-time data updates via WebSocket connection for select sensors:

- **Water Current Flow**: Updates in real-time as water flow changes
- **Other sensors**: Continue to use the configured polling interval for updates

This provides the best of both worlds:
- **Real-time responsiveness** for critical flow monitoring
- **Efficient polling** for less time-sensitive data like salt levels and regeneration status

The WebSocket connection is automatically managed by Home Assistant and will reconnect if the connection is lost.

## Water Shutoff Valve Control

The integration now includes remote control of the water shutoff valve through both a sensor (showing current state) and a switch (for control). This allows you to:

- Monitor the current state of your water shutoff valve
- Remotely shut off water supply in case of emergency
- Integrate valve control into Home Assistant automations

**Important Safety Note:** The water shutoff valve control is intended for emergency use and maintenance purposes. Always ensure you understand the implications of shutting off your water supply before using this feature.

### Example Automations

Here are some example automations you can create:

**Emergency Water Shutoff:**
```yaml
alias: "Emergency Water Shutoff"
trigger:
  - platform: state
    entity_id: binary_sensor.water_leak_detector
    to: "on"
action:
  - service: switch.turn_off
    target:
      entity_id: switch.iqua_softener_water_shutoff_valve
  - service: notify.mobile_app_your_phone
    data:
      message: "Water leak detected! Water supply has been shut off."
```

**Water Usage Alert with Auto Shutoff:**
```yaml
alias: "High Water Usage Alert"
trigger:
  - platform: numeric_state
    entity_id: sensor.iqua_softener_water_current_flow
    above: 50  # Adjust threshold as needed
    for:
      minutes: 30
action:
  - service: switch.turn_off
    target:
      entity_id: switch.iqua_softener_water_shutoff_valve
  - service: notify.mobile_app_your_phone
    data:
      message: "Unusually high water flow detected for 30 minutes. Water supply has been shut off as a precaution."
```

## Installation

### Method 1: HACS (Recommended)

**Note: This integration includes a vendored copy of the required library, so no additional manual installation is needed.**

1. **Install HACS** if you haven't already:
   - Follow the [HACS installation guide](https://hacs.xyz/docs/setup/download)

2. **Add this repository to HACS**:
   - Go to HACS in your Home Assistant
   - Click on "Integrations"
   - Click the three dots menu (⋮) in the top right
   - Select "Custom repositories"
   - Add repository URL: `https://github.com/jmacul2/homeassistant-iqua-softener`
   - Select category: "Integration"
   - Click "Add"

3. **Install the integration**:
   - Search for "iQua Softener" in HACS
   - Click "Download"
   - Restart Home Assistant

### Method 2: Manual Installation

Copy the `custom_components/iqua_softener` folder into your Home Assistant `config/custom_components` directory.

**Directory structure should look like:**
```
config/
  custom_components/
    iqua_softener/
      __init__.py
      config_flow.py
      const.py
      manifest.json
      sensor.py
      switch.py
      strings.json
      vendor/          # Vendored iqua-softener library
        iqua_softener/
      translations/
        en.json
```

After installation (either method), restart Home Assistant.

### About the Vendored Library

This integration currently includes a vendored copy of the `iqua-softener` library with enhanced WebSocket and authentication features. This approach:

- **Eliminates manual installation** - No need to manually install the library
- **Ensures compatibility** - The exact version with required features is included
- **Simplifies deployment** - Users only need to install the integration itself

The vendored library will be removed once the upstream changes are merged and published to PyPI.

## Prerequisites

- Home Assistant 2023.1.0 or newer
- Active iQua account with water softener registered
- Network connectivity for your Home Assistant instance

## Configuration
To add an iQua water softener to Home assistant, go to Settings and click "+ ADD INTEGRATION" button. From list select "iQua Softener" and click it, in displayed window you must enter:
- Username - username for iQua application
- Password - password for iQua application
- Serial number - device serial number, you can find it in iQua app device information tab and field called "DSN#" (this field is case sensitive!)
- Update Interval (minutes) - how often to poll the iQua servers for updated data (default: 5 minutes, range: 1-60 minutes)
- Enable Real-time Updates - enable WebSocket connection for real-time data updates (default: enabled)

### Configuration Options

After initial setup, you can modify settings by:
1. Go to **Settings → Devices & Services**
2. Find your iQua Softener integration
3. Click **"Configure"** or the options button (⋯)
4. Adjust the update interval or toggle real-time updates

## Troubleshooting

### Common Issues

**Integration not appearing in HACS:**
- Ensure you've added the custom repository URL correctly
- Check that the category is set to "Integration"
- Refresh HACS and try searching again

**Authentication errors:**
- Verify your iQua app credentials are correct
- Ensure your device serial number (DSN#) is entered exactly as shown in the iQua app
- Check that your iQua account has access to the water softener

**No real-time updates:**
- Check if "Enable Real-time Updates" is enabled in integration options
- Verify your Home Assistant has internet connectivity
- Check the logs for WebSocket connection errors

**Sensors showing as unavailable:**
- Check Home Assistant logs for API errors
- Verify the device serial number is correct
- Ensure the water softener is online in the iQua app

### Enable Debug Logging

To help diagnose issues, add this to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.iqua_softener: debug
```

Then restart Home Assistant and check the logs under **Settings → System → Logs**.

## License
[MIT](https://choosealicense.com/licenses/mit/)
