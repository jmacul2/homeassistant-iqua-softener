# iQua app supported water softeners integration for Home Assistant

`iqua_softener` is a _custom component_ for [Home Assistant](https://www.home-assistant.io/). The integration allows you to pull data for you iQua app supported water softener from Ecowater company server.

It will create ten sensors (refreshed based on your configured update interval, default 1 minute):
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
Copy the `custom_components/iqua_softener` folder into the config folder.

## Configuration
To add an iQua water softener to Home assistant, go to Settings and click "+ ADD INTEGRATION" button. From list select "iQua Softener" and click it, in displayed window you must enter:
- Username - username for iQua application
- Password - password for iQua application
- Serial number - device serial number, you can find it in iQua app device information tab and field called "DSN#" (this field is case sensitive!)
- Update Interval (minutes) - how often to poll the iQua servers for updated data (default: 1 minute, range: 1-60 minutes)

## License
[MIT](https://choosealicense.com/licenses/mit/)
