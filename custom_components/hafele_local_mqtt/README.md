# Hafele Local MQTT Home Assistant Integration

This integration provides Home Assistant support for Hafele LED lights via MQTT using local control.

## Features

- Auto-discovery of Hafele devices from MQTT topics
- Light control (on/off, brightness)
- Status polling to keep device states up to date
- Support for groups and scenes (optional)

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Install "Hafele Local MQTT" from HACS
3. Restart Home Assistant
4. Go to Settings > Devices & Services > Add Integration
5. Search for "Hafele Local MQTT" and follow the setup wizard

### Manual Installation

1. Clone or download this repository
2. Copy the `custom_components/hafele_local_mqtt` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant
4. Go to Settings > Devices & Services > Add Integration
5. Search for "Hafele Local MQTT" and follow the setup wizard

## Configuration

The integration requires:
- An MQTT broker configured in Home Assistant
- Hafele devices configured to publish to MQTT topics

### MQTT Topics

The integration subscribes to these discovery topics:
- `hafele/lights` - JSON array of light devices
- `hafele/groups` - JSON array of groups
- `hafele/scenes` - JSON array of scenes

### Control Topics

The integration publishes commands to:
- `hafele/device/{device_addr}/set` - Control individual lights
- `hafele/device/{device_addr}/get` - Request device status

### Status Topics

The integration subscribes to:
- `hafele/device/{device_addr}/status` or `hafele/device/{device_addr}/response` - Device status responses

**Note:** The exact topic patterns may need to be adjusted based on your Hafele MQTT API documentation.

## Polling

Since Hafele devices don't automatically publish state updates, the integration uses a polling mechanism:
- Default polling interval: 60 seconds
- Default polling timeout: 5 seconds
- Configurable in the integration settings

## Troubleshooting

If devices are not discovered:
1. Verify MQTT broker is connected in Home Assistant
2. Check that Hafele devices are publishing to the discovery topics
3. Check Home Assistant logs for errors

If status updates are not working:
1. Verify the status response topic matches your Hafele API
2. Adjust polling interval/timeout in integration settings
3. Check MQTT broker logs for message flow

## Support

For issues and feature requests, please open an issue on [GitHub](https://github.com/josephyanks/ha-hafele-mqtt-integration/issues).

