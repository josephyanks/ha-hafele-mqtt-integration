# AI Agent README - Hafele Local MQTT Integration

This document provides comprehensive information for AI agents working with this Home Assistant custom integration codebase.

## Repository Overview

**Purpose:** Home Assistant custom integration for controlling Hafele LED lights via MQTT using local control.

**Key Requirements:**
- Requires a "Gateway, Häfele Connect Mesh" device as a bridge between Bluetooth LE network and MQTT
- Home Assistant 2024.1 or later
- MQTT broker configured in Home Assistant
- Integration is in alpha stage and should be considered unstable

**Domain:** `hafele_local_mqtt`  
**Integration Type:** `hub`  
**IoT Class:** `local_push`  
**Version:** 1.0.3 (from manifest.json)

## Architecture

### Core Components

1. **`__init__.py`**: Integration setup and entry point
   - Sets up MQTT client and discovery
   - Manages config entry lifecycle
   - Initializes platforms (LIGHT, BUTTON)

2. **`config_flow.py`**: Configuration UI for user setup
   - Handles MQTT broker configuration (can use HA's MQTT or external)
   - Configures topic prefix, polling intervals, timeouts
   - Options for enabling/disabling groups and scenes

3. **`discovery.py`**: Device discovery from MQTT topics
   - Subscribes to discovery topics (`lights`, `groups`, `scenes`)
   - Processes discovery messages and updates device registry

4. **`mqtt_client.py`**: MQTT client wrapper
   - Handles connection to MQTT broker (HA's MQTT integration or external)
   - Manages subscriptions and message publishing
   - Uses `aiomqtt>=2.0.0` library

5. **`light.py`**: Light platform with polling coordinator
   - Implements Home Assistant light entities
   - Handles status polling (devices don't auto-publish updates)
   - Manages state updates from MQTT status topics

6. **`button.py`**: Button platform for scene activation
   - Provides buttons for scene recall operations

7. **`const.py`**: Constants and MQTT topic patterns
   - All topic templates and configuration keys
   - Default values and constants

### Data Flow

1. **Discovery**: Integration subscribes to `{gateway_topic}/lights`, `{gateway_topic}/groups`, `{gateway_topic}/scenes`
2. **Status Polling**: Integration periodically publishes GET requests and subscribes to status responses
3. **Control**: User actions in HA trigger MQTT command publications to control topics

## Hafele MQTT API Information

### API Source

The integration uses the **Hafele MQTT API for Connect Mesh** (version 0.2.0):
- Official Documentation: https://help.connect-mesh.io/mqtt/
- API Reference: https://help.connect-mesh.io/mqtt/index.html

### Important API Concepts

**Operation IDs vs Topic Names:**
- **Operation IDs** (like `setDevicePower`, `getDevicePower`) are **ONLY for API documentation lookup**
- They are **NEVER used in actual MQTT topic names**
- Actual topic names follow patterns like: `{gateway_topic}/lights/{device_name}/power`

**Topic Structure:**
- Device topics: `{gateway_topic}/lights/{device_name}/{topic_name}`
- Group topics: `{gateway_topic}/groups/{group_name}/{topic_name}`
- Scene topics: `{gateway_topic}/scenes/{scene_name}/activate`
- Default gateway topic: `hafele` (configurable)

**Device Names in Topics:**
- Device names may need URL encoding if they contain spaces or special characters
- Example: `"Scullery lower right"` → `"Scullery%20lower%20right"`

**Topic Naming Patterns:**
- SET operations: Use property name directly (e.g., `power`, `lightness`, `temperature`)
- GET operations: Use property name + "Get" (e.g., `powerGet`, `lightnessGet`, `hslGet`)

**Status Response Topics:**
- GET operations don't have separate response topics
- Device status: `{gateway_topic}/lights/{device_name}/status`
- Group status: `{gateway_topic}/groups/{group_name}/status`

**Power State Format:**
- Commands use: `"onOff": "on"` or `"onOff": "off"` (camelCase, string values)
- Status responses use: `"onoff": 1` or `"onoff": 0` (lowercase, numeric values)
- **Note:** There's an inconsistency - lightStatus uses lowercase `"onoff"` with numeric values, while groupStatus uses camelCase `"onOff"` with string values

## Detailed API Operations

### Discovery Operations (RECEIVE - Subscribe)

#### lightsDiscovery
- **Topic:** `{gateway_topic}/lights`
- **Payload:** JSON array of light devices
```json
[
  {
    "device_name": "string",
    "location": "string",
    "device_addr": 0,
    "device_types": ["light", "multiwhite", "rgb"]
  }
]
```

#### groupDiscovery
- **Topic:** `{gateway_topic}/groups`
- **Payload:** JSON array of groups
```json
[
  {
    "group_name": "string",
    "devices": [0],
    "group_main_addr": 0
  }
]
```

#### sceneDiscovery
- **Topic:** `{gateway_topic}/scenes`
- **Payload:** JSON array of scenes
```json
[
  {
    "scene": "string",
    "groups": [0]
  }
]
```

### Status Operations (RECEIVE - Subscribe)

#### lightStatus
- **Topic:** `{gateway_topic}/lights/{device_name}/status`
- **Payload:**
```json
{
  "device_name": "string",
  "onoff": 1,  // Note: lowercase, numeric (1=on, 0=off)
  "lightness": 0.0-1.0,
  "temperature": 800-20000,
  "hue": 0-360,
  "saturation": 0.0-1.0
}
```

#### groupStatus
- **Topic:** `{gateway_topic}/groups/{group_name}/status`
- **Payload:**
```json
{
  "group_name": "string",
  "onOff": "on" | "off",  // Note: camelCase, string values
  "lightness": 0.0-1.0,
  "temperature": 800-20000,
  "hue": 0-360,
  "saturation": 0.0-1.0
}
```

### Device Control Operations (SEND - Publish)

#### Power Control
- **setDevicePower**: `{gateway_topic}/lights/{device_name}/power`
  - Payload: `{"onOff": "on" | "off"}`
- **getDevicePower**: `{gateway_topic}/lights/{device_name}/powerGet`
  - Payload: `{}`
  - Response on: `{gateway_topic}/lights/{device_name}/status`

#### Lightness Control
- **setDeviceLightness**: `{gateway_topic}/lights/{device_name}/lightness`
  - Payload: `{"lightness": 0.0-1.0, "transition_time": 0-372000}`
- **getDeviceLightness**: `{gateway_topic}/lights/{device_name}/lightnessGet`
  - Payload: `{}`

#### Color Temperature Control
- **setDeviceTemperature**: `{gateway_topic}/lights/{device_name}/temperature`
  - Payload: `{"temperature": 800-20000, "transition_time": 0-372000}`
  - **⚠️ IMPORTANT:** This operation is NOT working for single lights (as of 01.2026). Use `setDeviceCtl` instead.
- **setDeviceCtl**: `{gateway_topic}/lights/{device_name}/ctl`
  - Payload: `{"lightness": 0.0-1.0, "temperature": 800-20000, "transition_time": 0-372000}`
- **getDeviceCtl**: `{gateway_topic}/lights/{device_name}/ctlGet`
  - Payload: `{}`

#### HSL Control
- **setDeviceHue**: `{gateway_topic}/lights/{device_name}/hue`
  - Payload: `{"hue": 0-360, "transition_time": 0-372000}`
- **setDeviceSaturation**: `{gateway_topic}/lights/{device_name}/saturation`
  - Payload: `{"saturation": 0.0-1.0, "transition_time": 0-372000}`
- **setDeviceHsl**: `{gateway_topic}/lights/{device_name}/hsl`
  - Payload: `{"hue": 0-360, "saturation": 0.0-1.0, "lightness": 0.0-1.0, "transition_time": 0-372000}`
- **getDeviceHsl**: `{gateway_topic}/lights/{device_name}/hslGet`
  - Payload: `{}`

### Group Control Operations (SEND - Publish)

Similar to device operations but use `{gateway_topic}/groups/{group_name}/` prefix:
- **setGroupPower**: `{gateway_topic}/groups/{group_name}/power`
- **getGroupPower**: `{gateway_topic}/groups/{group_name}/powerGet`
- **setGroupLightness**: `{gateway_topic}/groups/{group_name}/lightness`
- **getGroupLightness**: `{gateway_topic}/groups/{group_name}/lightnessGet`
- **setGroupTemperature**: `{gateway_topic}/groups/{group_name}/temperature`
- **setGroupCtl**: `{gateway_topic}/groups/{group_name}/ctl`
- **setGroupHue**: `{gateway_topic}/groups/{group_name}/hue`
- **setGroupSaturation**: `{gateway_topic}/groups/{group_name}/saturation`
- **setGroupHsl**: `{gateway_topic}/groups/{group_name}/hsl`
- **getGroupHsl**: `{gateway_topic}/groups/{group_name}/hslGet`

### Scene Operations (SEND - Publish)

#### recallScene
- **Topic:** `{gateway_topic}/scenes/{scene_name}/activate`
- **Payload:** `{"transition_time": 0-372000}`

#### recallSceneGroup
- **Topic:** `{gateway_topic}/scenes/{scene_name}/activate`
- **Payload:** `{"group_id": 0, "transition_time": 0-372000}`

#### recallSceneDevice
- **Topic:** `{gateway_topic}/scenes/{scene_name}/activate`
- **Payload:** `{"device_name": "string", "transition_time": 0-372000}`

### Value Ranges and Constraints

- **Lightness**: 0.0 to 1.0 (0-100%)
- **Temperature**: 800 to 20000 Kelvin
- **Hue**: 0 to 360 degrees
- **Saturation**: 0.0 to 1.0 (0-100%)
- **Transition Time**: 0 to 372000 deciseconds (0.1s units)
  - The API may round down to nearest supported increment per BLE Mesh Specification Section 3.1.3:
    - 0.1s steps: 0-6.2s
    - 1s steps: 0-62s
    - 10s steps: 1-10.5 minutes
    - 10-minute steps: up to 10.5 hours

## Code Structure

### File Organization

```
custom_components/hafele_local_mqtt/
├── __init__.py          # Integration entry point and setup
├── config_flow.py       # Configuration UI and flow
├── discovery.py         # MQTT discovery handler
├── mqtt_client.py       # MQTT client wrapper
├── light.py             # Light platform implementation
├── button.py            # Button platform for scenes
├── const.py             # Constants and topic patterns
├── strings.json         # UI strings for config flow
├── manifest.json        # Integration metadata
└── logo/
    └── icon.png         # Integration icon
```

### Key Constants (from const.py)

- `DOMAIN = "hafele_local_mqtt"`
- `DEFAULT_TOPIC_PREFIX = "hafele"`
- `DEFAULT_POLLING_INTERVAL = 60` (seconds)
- `DEFAULT_POLLING_TIMEOUT = 5` (seconds)
- `DEFAULT_MQTT_PORT = 1883`

### Configuration Options

- `topic_prefix`: MQTT topic prefix (default: "hafele")
- `polling_interval`: Status polling interval in seconds (default: 60)
- `polling_timeout`: Timeout for status requests in seconds (default: 5)
- `enable_groups`: Enable/disable group entities (boolean)
- `enable_scenes`: Enable/disable scene entities (boolean)
- `use_ha_mqtt`: Use Home Assistant's MQTT integration (default: True)
- `mqtt_broker`: External MQTT broker host (if not using HA MQTT)
- `mqtt_port`: MQTT broker port (default: 1883)
- `mqtt_username`: MQTT broker username (optional)
- `mqtt_password`: MQTT broker password (optional)

## Implementation Details

### Polling Mechanism

Since Hafele devices don't automatically publish state updates, the integration uses polling:
1. Publishes status requests (GET operations) to each device at regular intervals
2. Subscribes to response topics to receive status updates
3. Updates entity states based on received responses

### MQTT Client Options

The integration can use either:
1. Home Assistant's built-in MQTT integration (default)
2. External MQTT broker (configured via config flow)

### Platform Support

- **Platform.LIGHT**: Light entities for individual devices and groups
- **Platform.BUTTON**: Button entities for scene activation

## Known Issues and Limitations

1. **Color Temperature for Multiwhite Lights**: 
   - Not settable on single light using `setDeviceTemperature`
   - Works on Group Temperature setting in MQTT
   - Use `setDeviceCtl` instead for single lights

2. **API/MQTT Mismatch**: 
   - Temperature data may not be available in MQTT light status responses
   - This is a known limitation of the API

3. **Performance Impact**: 
   - High polling rates or large networks can decrease response time of buttons/inputs
   - Caused by high Bluetooth LE traffic

4. **Power State Format Inconsistency**:
   - `lightStatus` uses lowercase `"onoff"` with numeric values (1/0)
   - `groupStatus` uses camelCase `"onOff"` with string values ("on"/"off")
   - Commands use camelCase `"onOff"` with string values

## Development Notes

### Dependencies

- `aiomqtt>=2.0.0` (for MQTT client)
- Home Assistant MQTT integration (optional, can use external broker)

### Home Assistant Integration Pattern

This follows Home Assistant's custom integration guidelines:
- Uses `config_flow` for setup
- Implements platform entities (light, button)
- Uses coordinator pattern for polling
- Stores data in `hass.data[DOMAIN][entry_id]`

### Testing Considerations

- Devices require actual Hafele gateway hardware
- MQTT broker must be accessible
- Discovery messages must be published by the gateway
- Status polling requires devices to respond to GET requests

## References

- Official Hafele MQTT API: https://help.connect-mesh.io/mqtt/
- API Operations Reference: See `API_OPERATIONS.md` in repository
- User Documentation: See `README.md` in repository
- Gateway Setup: https://help.connect-mesh.io/docs/smarthome/gateway-setup
- Local MQTT Setup: https://help.connect-mesh.io/docs/professional/mqtt

## Quick Reference for AI Agents

When working with this codebase:

1. **Topic Construction**: Always use `const.py` topic templates with `.format()` or f-strings
2. **Device Names**: May need URL encoding - check if spaces/special chars present
3. **Power States**: Handle both numeric (status) and string (commands) formats
4. **Temperature Control**: Use `ctl` operations for single lights, not `temperature`
5. **Status Updates**: Always subscribe to status topics, never assume auto-updates
6. **Polling**: Required for state synchronization - devices don't push updates
7. **Operation IDs**: Never use in code - they're documentation-only references

