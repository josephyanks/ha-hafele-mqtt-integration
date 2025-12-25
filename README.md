# Home Assistant Hafele MQTT Integration

[![GitHub release](https://img.shields.io/github/release/josephyanks/ha-hafele-mqtt-integration.svg)](https://github.com/josephyanks/ha-hafele-mqtt-integration/releases)
[![License](https://img.shields.io/github/license/josephyanks/ha-hafele-mqtt-integration.svg)](LICENSE)

<img src="./custom_components/hafele_local_mqtt/logo/icon.png" height="128" width="128" />

Home Assistant custom integration for controlling Hafele LED lights via MQTT using local control.
You need a "Gateway, Häfele Connect Mesh" which will be the bridge between the Bluetooth LE network and the MQTT.

Please note that this should be considered unstable and is definitely in an alpha stage. 

**Important:** When installing this integration in Home Assistant, you need to copy the entire `custom_components/hafele_local_mqtt/` folder to your Home Assistant's `custom_components/` directory. The `custom_components/` folder structure is required for Home Assistant to recognize the integration.

## Features

- ✅ Auto-discovery of Hafele devices from MQTT topics
- ✅ Light control (on/off, brightness)
- ✅ Status polling to keep device states up to date
- ✅ Configurable polling intervals

## Installation

The first part of installation should be enabling the MQTT functionality on your hafele devices. Please follow directions found in this github issue: [https://github.com/qnimbus/haefele-connect-mesh/issues/2](https://github.com/qnimbus/haefele-connect-mesh/issues/2) and the official documentation [https://help.connect-mesh.io/docs/smarthome/gateway-setup](https://help.connect-mesh.io/docs/smarthome/gateway-setup)

I ended up installing Mosquito Broker and MQTT Explorer on my HA instance as well to facilitate the installation.

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to Integrations
3. Click the three dots menu (⋮) in the top right
4. Select "Custom repositories"
5. Add repository: `https://github.com/josephyanks/ha-hafele-mqtt-integration`
6. Select category: "Integration"
7. Click "Add"
8. Find "Hafele Local MQTT" in HACS and install it
9. Restart Home Assistant
10. Go to Settings > Devices & Services > Add Integration
11. Search for "Hafele Local MQTT" and follow the setup wizard

### Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/hafele_local_mqtt` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant
4. Go to Settings > Devices & Services > Add Integration
5. Search for "Hafele Local MQTT" and follow the setup wizard

## Requirements

- Home Assistant 2024.1 or later
- MQTT broker configured in Home Assistant
- Hafele devices configured to publish to MQTT topics

## Configuration

The integration will guide you through setup via the config flow. You can configure:

- MQTT topic prefix (default: `hafele`)
- Polling interval (default: 60 seconds)
- Polling timeout (default: 5 seconds)
- Enable/disable group entities
- Enable/disable scene entities

## MQTT Topics

The integration uses the following MQTT topics:

### Discovery Topics (Subscribed)
- `hafele/lights` - JSON array of light devices
- `hafele/groups` - JSON array of groups
- `hafele/scenes` - JSON array of scenes

### Control Topics (Published)
- `hafele/device/{device_addr}/set` - Control individual lights
- `hafele/device/{device_addr}/get` - Request device status

### Status Topics (Subscribed)
- `hafele/device/{device_addr}/status` or `hafele/device/{device_addr}/response` - Device status responses

**Note:** The exact topic patterns may need to be adjusted based on your Hafele MQTT API documentation. You can modify these in `custom_components/hafele_local_mqtt/const.py` if needed.

## How It Works

Uses the kind-of-public [Hafele MQTT api for connect mesh](https://help.connect-mesh.io/mqtt/)

1. **Discovery**: The integration subscribes to MQTT discovery topics (`hafele/lights`, `hafele/groups`, `hafele/scenes`) to automatically discover your Hafele devices.

2. **Status Polling**: Since Hafele devices don't automatically publish state updates, the integration uses a polling mechanism:
   - Publishes status requests to each device at regular intervals
   - Subscribes to response topics to receive status updates
   - Updates entity states based on received responses

3. **Control**: When you control a light in Home Assistant, the integration publishes MQTT commands to the appropriate control topic.

## Troubleshooting

### Devices Not Discovered
1. Verify MQTT broker is connected in Home Assistant
2. Check that Hafele devices are publishing to the discovery topics
3. Use an MQTT client to verify messages are being published
4. Check Home Assistant logs for errors

### Status Updates Not Working
1. Verify the status response topic matches your Hafele API
2. Adjust polling interval/timeout in integration settings
3. Check MQTT broker logs for message flow
4. Verify device addresses match between discovery and status topics

### Integration Not Appearing
1. Ensure the folder structure is correct: `config/custom_components/hafele_local_mqtt/`
2. Check that all files are present in the integration folder
3. Restart Home Assistant completely
4. Check Home Assistant logs for import errors

### Known Bugs
1. Color Temperature of Multiwhite lights not settable on single light / but working on Group Temperature setting in MQTT
2. API / MQTT mismatch -> nowhere in the mqtt light temperature data is available
3. Due to high polling rates or big networks the response time of buttons/inputs will decrease due to high bluetooh LE traffic

## Development

This integration is built following Home Assistant's custom integration guidelines. Key components:

- **`__init__.py`**: Integration setup and entry point
- **`config_flow.py`**: Configuration UI
- **`discovery.py`**: Device discovery from MQTT topics
- **`mqtt_client.py`**: MQTT client wrapper
- **`light.py`**: Light platform with polling coordinator
- **`const.py`**: Constants and MQTT topic patterns

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues, questions, or feature requests, please open an issue on [GitHub](https://github.com/josephyanks/ha-hafele-mqtt-integration/issues).

## Acknowledgments

This absolutely wouldn't have been possible without the work done by individuals in [https://github.com/qnimbus/haefele-connect-mesh/issues/2](https://github.com/qnimbus/haefele-connect-mesh/issues/2) - specifically to [@qnimbus](https://github.com/qnimbus) for reaching out to Hafele and figuring out about the firmware / internal mqtt api.

- Inspired by the [ha-shellies-discovery](https://github.com/bieniu/ha-shellies-discovery) project
- Built for the Home Assistant community

