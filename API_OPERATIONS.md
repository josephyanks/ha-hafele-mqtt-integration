# Häfele Connect MQTT API Operations Reference

This document lists all available operations in the Häfele Connect MQTT API v0.2.0, based on the official documentation at [help.connect-mesh.io](https://help.connect-mesh.io/mqtt/index.html).

## Important Note About Operation IDs

**Operation IDs** (like `setDevicePower`, `getDevicePower`, etc.) are **ONLY for API documentation lookup purposes**. They are **NEVER used in actual MQTT topic names**. The actual topic names follow different patterns as documented below.

## Topic Structure

All topics use the format: `{gateway_topic}/lights/{device_name}/{topic_name}` or `{gateway_topic}/groups/{group_name}/{topic_name}`.

Where `{gateway_topic}` is the root topic configured for your gateway (default: `hafele`).

**Important note about groups vs devices:**

- **Groups** are a **routing convenience** in the MQTT API. Group *commands* use the `{gateway_topic}/groups/{group_name}/{topic_name}` pattern.
- **Status and state are always reported per device** on `{gateway_topic}/lights/{device_name}/status`. There is effectively **no separate group status topic** in the live gateway behavior, even though the API documentation suggests one.
- Integrations are expected to **derive group state** (on/off, brightness, color temperature, etc.) by aggregating the states of member devices.

## Discovery Operations (RECEIVE - Subscribe)

### RECEIVE lightsDiscovery
**Operation ID:** `lightsDiscovery`  
**Topic:** `{gateway_topic}/lights`

**Description:** Receives information about discovered lights in the network.

**Payload Format:**
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

**Parameters:**
- `device_name` (string, required): The name of the device
- `location` (string, required): Location of the device
- `device_addr` (integer, required): The address of the device
- `device_types` (array of strings, required): The types of lights the device has
  - Allowed values: `"light"`, `"multiwhite"`, `"rgb"`

---

### RECEIVE groupDiscovery
**Operation ID:** `groupDiscovery`  
**Topic:** `{gateway_topic}/groups`

**Description:** Receives information about discovered groups in the network.

**Payload Format:**
```json
[
  {
    "group_name": "string",
    "devices": [0],
    "group_main_addr": 0
  }
]
```

**Parameters:**
- `group_name` (string, required): Name of the group
- `devices` (array of integers, required): List of device addresses in the group
- `group_main_addr` (integer, required): Main address of the group

---

### RECEIVE sceneDiscovery
**Operation ID:** `sceneDiscovery`  
**Topic:** `{gateway_topic}/scenes`

**Description:** Receives information about discovered scenes in the network.

**Payload Format:**
```json
[
  {
    "scene": "string",
    "groups": [0]
  }
]
```

**Parameters:**
- `scene` (string, required): Escaped name of the scene
- `groups` (array of integers, required): List of group IDs (main addresses) for the scene

---

## Status Operations (RECEIVE - Subscribe)

### RECEIVE lightStatus
**Operation ID:** `lightStatus`  
**Topic:** `{gateway_topic}/lights/{device_name}/status`

**Description:** Receives status updates from light devices.

**Payload Format:**
```json
{
  "device_name": "string",
  "onoff": 1,
  "lightness": 0.0-1.0,
  "temperature": 800-20000,
  "hue": 0-360,
  "saturation": 0.0-1.0
}
```

**Parameters:**
- `device_name` (string): Name of the light device
- `onoff` (integer): Power state - `1` for on, `0` for off (note: status responses use numeric format, commands use string format)
- `lightness` (number, 0-1): Lightness level (0.0 to 1.0)
- `temperature` (integer, 800-20000): Color temperature in Kelvin
- `hue` (integer, 0-360): Hue value
- `saturation` (number, 0-1): Saturation level (0.0 to 1.0)

**Note:** Status responses use `"onoff"` (lowercase) with numeric values (1/0), while commands use `"onOff"` (camelCase) with string values ("on"/"off").

---

### RECEIVE groupStatus (theoretical)
**Operation ID:** `groupStatus`  
**Topic:** `{gateway_topic}/groups/{group_name}/status`

**Description:** The official API describes a group status topic. In practice, the Häfele gateway reports status **only on individual device topics** (`{gateway_topic}/lights/{device_name}/status`) even when you perform operations against a group.

**Practical usage note:**

- Treat this section as **documentation of the intended contract only**.  
- When you send **GET operations to group topics** (e.g. `getGroupPower`, `getGroupLightness`, `getGroupCtl`), the resulting status messages appear on **each member device’s** status topic, not on `{gateway_topic}/groups/{group_name}/status`.
- Client integrations must compute group state (on/off, lightness, color temperature, etc.) by **aggregating the member device states**.

The payload shape for a hypothetical group status is analogous to the device status payload, but you should not rely on `{gateway_topic}/groups/{group_name}/status` being used by the gateway.

## Device Control Operations (SEND - Publish)

### SEND setDevicePower
**Operation ID:** `setDevicePower`  
**Topic:** `{gateway_topic}/lights/{device_name}/power`

**Description:** Sets the power state of a specific device.

**Payload Format:**
```json
{
  "onOff": "on" | "off"
}
```

**Parameters:**
- `onOff` (string, required): Desired power state - `"on"` or `"off"`

---

### SEND getDevicePower
**Operation ID:** `getDevicePower`  
**Topic:** `{gateway_topic}/lights/{device_name}/powerGet`

**Description:** Requests the current power state of a specific device.

**Payload Format:**
```json
{}
```

**Note:** Response is received on `{gateway_topic}/lights/{device_name}/status`

---

### SEND setDeviceLightness
**Operation ID:** `setDeviceLightness`  
**Topic:** `{gateway_topic}/lights/{device_name}/lightness`

**Description:** Sets the lightness level of a specific device.

**Payload Format:**
```json
{
  "lightness": 0.0-1.0,
  "transition_time": 0-372000
}
```

**Parameters:**
- `lightness` (number, required, 0-1): Desired lightness level (0.0 to 1.0)
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds (0.1s)

---

### SEND getDeviceLightness
**Operation ID:** `getDeviceLightness`  
**Topic:** `{gateway_topic}/lights/{device_name}/lightnessGet`

**Description:** Requests the current lightness level of a specific device.

**Payload Format:**
```json
{}
```

**Note:** Response is received on `{gateway_topic}/lights/{device_name}/status`

---

### SEND setDeviceTemperature
**Operation ID:** `setDeviceTemperature`  
**Topic:** `{gateway_topic}/lights/{device_name}/temperature`

**Description:** Sets the color temperature of a specific device.

**Payload Format:**
```json
{
  "temperature": 800-20000,
  "transition_time": 0-372000
}
```

**Parameters:**
- `temperature` (integer, required, 800-20000): Desired color temperature in Kelvin
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND setDeviceHue
**Operation ID:** `setDeviceHue`  
**Topic:** `{gateway_topic}/lights/{device_name}/hue`

**Description:** Sets the hue of a specific device.

**Payload Format:**
```json
{
  "hue": 0-360,
  "transition_time": 0-372000
}
```

**Parameters:**
- `hue` (integer, required, 0-360): Desired hue value
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND setDeviceSaturation
**Operation ID:** `setDeviceSaturation`  
**Topic:** `{gateway_topic}/lights/{device_name}/saturation`

**Description:** Sets the saturation of a specific device.

**Payload Format:**
```json
{
  "saturation": 0.0-1.0,
  "transition_time": 0-372000
}
```

**Parameters:**
- `saturation` (number, required, 0-1): Desired saturation level (0.0 to 1.0)
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND setDeviceHsl
**Operation ID:** `setDeviceHsl`  
**Topic:** `{gateway_topic}/lights/{device_name}/hsl`

**Description:** Sets the hue, saturation, and lightness of a specific device.

**Payload Format:**
```json
{
  "hue": 0-360,
  "saturation": 0.0-1.0,
  "lightness": 0.0-1.0,
  "transition_time": 0-372000
}
```

**Parameters:**
- `hue` (integer, required, 0-360): Desired hue value
- `saturation` (number, required, 0-1): Desired saturation level
- `lightness` (number, required, 0-1): Desired lightness level
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND getDeviceHsl
**Operation ID:** `getDeviceHsl`  
**Topic:** `{gateway_topic}/lights/{device_name}/hslGet`

**Description:** Requests the current hue, saturation, and lightness of a specific device.

**Payload Format:**
```json
{}
```

**Note:** Response is received on `{gateway_topic}/lights/{device_name}/status`

---

### SEND setDeviceCtl
**Operation ID:** `setDeviceCtl`  
**Topic:** `{gateway_topic}/lights/{device_name}/ctl`

**Description:** Sets the color temperature and lightness of a specific device.

**Payload Format:**
```json
{
  "lightness": 0.0-1.0,
  "temperature": 800-20000,
  "transition_time": 0-372000
}
```

**Parameters:**
- `lightness` (number, required, 0-1): Desired lightness level
- `temperature` (integer, required, 800-20000): Desired color temperature in Kelvin
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND getDeviceCtl
**Operation ID:** `getDeviceCtl`  
**Topic:** `{gateway_topic}/lights/{device_name}/ctlGet`

**Description:** Requests the current color temperature and lightness of a specific device.

**Payload Format:**
```json
{}
```

**Note:** Response is received on `{gateway_topic}/lights/{device_name}/status`

---

## Group Control Operations (SEND - Publish)

### SEND setGroupPower
**Operation ID:** `setGroupPower`  
**Topic:** `{gateway_topic}/groups/{group_name}/power`

**Description:** Sets the power state of a group.

**Payload Format:**
```json
{
  "onOff": "on" | "off"
}
```

**Parameters:**
- `onOff` (string, required): Desired power state - `"on"` or `"off"`

---

### SEND getGroupPower
**Operation ID:** `getGroupPower`  
**Topic:** `{gateway_topic}/groups/{group_name}/powerGet`

**Description:** Requests the current power state of a group.

**Payload Format:**
```json
{}
```

**Note:** In practice, responses are received on the individual device status topics  
`{gateway_topic}/lights/{device_name}/status` for each device in the group, **not** on a group status topic.

---

### SEND setGroupLightness
**Operation ID:** `setGroupLightness`  
**Topic:** `{gateway_topic}/groups/{group_name}/lightness`

**Description:** Sets the lightness level of a group.

**Payload Format:**
```json
{
  "lightness": 0.0-1.0,
  "transition_time": 0-372000
}
```

**Parameters:**
- `lightness` (number, required, 0-1): Desired lightness level
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND getGroupLightness
**Operation ID:** `getGroupLightness`  
**Topic:** `{gateway_topic}/groups/{group_name}/lightnessGet`

**Description:** Requests the current lightness level of a group.

**Payload Format:**
```json
{}
```

**Note:** In practice, responses are received on the individual device status topics  
`{gateway_topic}/lights/{device_name}/status` for each device in the group, **not** on a group status topic.

---

### SEND setGroupTemperature
**Operation ID:** `setGroupTemperature`  
**Topic:** `{gateway_topic}/groups/{group_name}/temperature`

**Description:** Sets the color temperature of a group.

**Payload Format:**
```json
{
  "temperature": 800-20000,
  "transition_time": 0-372000
}
```

**Parameters:**
- `temperature` (integer, required, 800-20000): Desired color temperature in Kelvin
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND setGroupHue
**Operation ID:** `setGroupHue`  
**Topic:** `{gateway_topic}/groups/{group_name}/hue`

**Description:** Sets the hue of a group.

**Payload Format:**
```json
{
  "hue": 0-360,
  "transition_time": 0-372000
}
```

**Parameters:**
- `hue` (integer, required, 0-360): Desired hue value
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND setGroupSaturation
**Operation ID:** `setGroupSaturation`  
**Topic:** `{gateway_topic}/groups/{group_name}/saturation`

**Description:** Sets the saturation of a group.

**Payload Format:**
```json
{
  "saturation": 0.0-1.0,
  "transition_time": 0-372000
}
```

**Parameters:**
- `saturation` (number, required, 0-1): Desired saturation level
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND setGroupHsl
**Operation ID:** `setGroupHsl`  
**Topic:** `{gateway_topic}/groups/{group_name}/hsl`

**Description:** Sets the hue, saturation, and lightness of a group.

**Payload Format:**
```json
{
  "hue": 0-360,
  "saturation": 0.0-1.0,
  "lightness": 0.0-1.0,
  "transition_time": 0-372000
}
```

**Parameters:**
- `hue` (integer, required, 0-360): Desired hue value
- `saturation` (number, required, 0-1): Desired saturation level
- `lightness` (number, required, 0-1): Desired lightness level
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND getGroupHsl
**Operation ID:** `getGroupHsl`  
**Topic:** `{gateway_topic}/groups/{group_name}/hslGet`

**Description:** Requests the current hue, saturation, and lightness of a group.

**Payload Format:**
```json
{}
```

**Note:** In practice, responses are received on the individual device status topics  
`{gateway_topic}/lights/{device_name}/status` for each device in the group, **not** on a group status topic.

---

### SEND setGroupCtl
**Operation ID:** `setGroupCtl`  
**Topic:** `{gateway_topic}/groups/{group_name}/ctl`

**Description:** Sets the color temperature and lightness of a group.

**Payload Format:**
```json
{
  "lightness": 0.0-1.0,
  "temperature": 800-20000,
  "transition_time": 0-372000
}
```

**Parameters:**
- `lightness` (number, required, 0-1): Desired lightness level
- `temperature` (integer, required, 800-20000): Desired color temperature in Kelvin
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND getGroupCtl
**Operation ID:** `getGroupCtl`  
**Topic:** `{gateway_topic}/groups/{group_name}/ctlGet`

**Description:** Requests the current color temperature and lightness of a group.

**Payload Format:**
```json
{}
```

**Note:** In practice, responses are received on the individual device status topics  
`{gateway_topic}/lights/{device_name}/status` for each device in the group, **not** on a group status topic.

---

## Scene Operations (SEND - Publish)

### SEND recallScene
**Operation ID:** `recallScene`  
**Topic:** `{gateway_topic}/scenes/{scene_name}/activate`

**Description:** Recalls/activates a specific scene.

**Payload Format:**
```json
{
  "transition_time": 0-372000
}
```

**Parameters:**
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND recallSceneLegacy
**Operation ID:** `recallSceneLegacy`  
**Topic:** `{gateway_topic}/scenes/{scene_name}/activate`

**Description:** Legacy method to recall a scene (uses scene ID instead of name).

**Payload Format:**
```json
{
  "scene_id": 0,
  "transition_time": 0-372000
}
```

**Parameters:**
- `scene_id` (integer, required): Identifier for the scene
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND recallSceneGroup
**Operation ID:** `recallSceneGroup`  
**Topic:** `{gateway_topic}/scenes/{scene_name}/activate`

**Description:** Recalls a scene for a specific group.

**Payload Format:**
```json
{
  "group_id": 0,
  "transition_time": 0-372000
}
```

**Parameters:**
- `group_id` (integer, required): Group identifier
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

### SEND recallSceneDevice
**Operation ID:** `recallSceneDevice`  
**Topic:** `{gateway_topic}/scenes/{scene_name}/activate`

**Description:** Recalls a scene for a specific device.

**Payload Format:**
```json
{
  "device_name": "string",
  "transition_time": 0-372000
}
```

**Parameters:**
- `device_name` (string, required): Name of the device
- `transition_time` (number, optional, 0-372000): Transition time in deciseconds

---

## Raw Message Operations

### SEND sendRawMessage
**Operation ID:** `sendRawMessage`  
**Topic:** `{gateway_topic}/rawMessage/send`

**Description:** Sends a raw access message to a specified destination.

**Payload Format:**
```json
{
  "destination": 0,
  "opcode": 0,
  "payload": "string"
}
```

**Parameters:**
- `destination` (number, required): Target device address
- `opcode` (number, required): Operation code
- `payload` (string, required): Hex-encoded payload string

---

### RECEIVE rawMessages
**Operation ID:** `rawMessages`  
**Topic:** `{gateway_topic}/rawMessage`

**Description:** Receives raw access messages from devices.

**Payload Format:**
```json
{
  "source": "string",
  "destination": "string",
  "opcode": "string",
  "payload": "string",
  "sequence_number": 0,
  "ttl": 0,
  "rssi": 0
}
```

**Parameters:**
- `source` (string, required): Hex-encoded source address
- `destination` (string, required): Hex-encoded destination address
- `opcode` (string, required): Hex-encoded operation code
- `payload` (string, required): Hex-encoded payload string
- `sequence_number` (number, required): Sequence number
- `ttl` (number, required): Time to live
- `rssi` (number, required): Received Signal Strength Indicator

---

## Network Configuration

### SEND setNetworkConfiguration
**Operation ID:** `setNetworkConfiguration`  
**Topic:** `{gateway_topic}/setNetworkConfiguration`

**Description:** Configures the network by specifying devices, groups, and scenes.

**Payload Format:**
```json
{
  "devices": [
    {
      "device_name": "string",
      "location": "string",
      "device_addr": 0,
      "device_types": ["light", "multiwhite", "rgb"]
    }
  ],
  "groups": [
    {
      "group_name": "string",
      "devices": [0],
      "group_main_addr": 0
    }
  ],
  "scenes": [
    {
      "scene": "string",
      "groups": [0]
    }
  ]
}
```

**Parameters:**
- `devices` (array of objects, required): List of devices in the network
  - `device_name` (string, required): Name of the device
  - `location` (string, required): Location of the device
  - `device_addr` (integer, required): Address of the device
  - `device_types` (array of strings, required): Types of lights (allowed: `"light"`, `"multiwhite"`, `"rgb"`)
- `groups` (array of objects, required): List of groups in the network
  - `group_name` (string, required): Name of the group
  - `devices` (array of integers, required): List of device addresses
  - `group_main_addr` (integer, required): Main address of the group
- `scenes` (array of objects, required): List of scenes in the network
  - `scene` (string, required): Escaped name of the scene
  - `groups` (array of integers, required): List of group IDs (main addresses)

---

## Important Notes

1. **Device Names in Topics:** Device names in topic paths may need URL encoding if they contain spaces or special characters (e.g., `"Scullery lower right"` → `"Scullery%20lower%20right"`).

2. **Transition Time:** Transition times are specified in deciseconds (0.1s units). The API may round down to the nearest supported increment per BLE Mesh Specification Section 3.1.3:
   - 0.1s steps: 0-6.2s
   - 1s steps: 0-62s
   - 10s steps: 1-10.5 minutes
   - 10-minute steps: up to 10.5 hours

3. **Status Responses:** GET operations don't have a separate response topic. Status is received on the corresponding status topics:
   - Device status: `{gateway_topic}/lights/{device_name}/status`
   - Group operations also result in status on **device** status topics (there is effectively no separate group status topic in practice).

4. **Value Ranges:**
   - Lightness: 0.0 to 1.0 (0-100%)
   - Temperature: 800 to 20000 Kelvin
   - Hue: 0 to 360 degrees
   - Saturation: 0.0 to 1.0 (0-100%)

5. **Power States:** Use string values `"on"` or `"off"` for power operations.

6. **Topic Naming Pattern:**
   - SET operations: Use the property name directly (e.g., `power`, `lightness`, `temperature`)
   - GET operations: Use property name + "Get" (e.g., `powerGet`, `lightnessGet`, `hslGet`)

---

## Reference

- Official API Documentation: https://help.connect-mesh.io/mqtt/index.html
- API Version: 0.2.0
