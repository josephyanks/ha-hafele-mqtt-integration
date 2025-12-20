# Home Assistant Hafele MQTT Integration

[![GitHub release](https://img.shields.io/github/release/josephyanks/ha-hafele-mqtt-integration.svg)](https://github.com/josephyanks/ha-hafele-mqtt-integration/releases)
[![License](https://img.shields.io/github/license/josephyanks/ha-hafele-mqtt-integration.svg)](LICENSE)

![Logo](./custom_components/hafele_local_mqtt/logo/icon.png)

Home Assistant custom integration for controlling Hafele LED lights via MQTT using local control.

## Repository Structure

This repository follows the standard Home Assistant custom integration structure:

```
ha-hafele-mqtt-integration/
├── custom_components/
│   └── hafele_local_mqtt/    # Integration code (this is what gets installed)
│       ├── __init__.py
│       ├── manifest.json
│       ├── config_flow.py
│       ├── const.py
│       ├── discovery.py
│       ├── light.py
│       ├── mqtt_client.py
│       ├── strings.json
│       └── README.md
├── README.md                    # This file (repository documentation)
└── .gitignore
```

**Important:** When installing this integration in Home Assistant, you need to copy the entire `custom_components/hafele_local_mqtt/` folder to your Home Assistant's `custom_components/` directory. The `custom_components/` folder structure is required for Home Assistant to recognize the integration.

## Features

- ✅ Auto-discovery of Hafele devices from MQTT topics
- ✅ Light control (on/off, brightness)
- ✅ Status polling to keep device states up to date
- ✅ Configurable polling intervals
- ✅ Support for groups and scenes (optional)

## Installation

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

- Inspired by the [ha-shellies-discovery](https://github.com/bieniu/ha-shellies-discovery) project
- Built for the Home Assistant community

