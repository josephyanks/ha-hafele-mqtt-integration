"""Constants for the Hafele Local MQTT integration."""

DOMAIN = "hafele_local_mqtt"

# MQTT Topic Prefix
DEFAULT_TOPIC_PREFIX = "hafele"

# Discovery Topics
TOPIC_LIGHTS = "lights"
TOPIC_GROUPS = "groups"
TOPIC_SCENES = "scenes"

# Polling Configuration
DEFAULT_POLLING_INTERVAL = 60  # seconds
DEFAULT_POLLING_TIMEOUT = 5  # seconds

# MQTT Topic Patterns - Verified against API documentation
# Reference: https://help.connect-mesh.io/mqtt/index.html

# Discovery topics (RECEIVE - Subscribe)
# API: RECEIVE lightsDiscovery, groupDiscovery, sceneDiscovery
TOPIC_DISCOVERY_LIGHTS = f"{{prefix}}/{TOPIC_LIGHTS}"  # {gateway_topic}/lights
TOPIC_DISCOVERY_GROUPS = f"{{prefix}}/{TOPIC_GROUPS}"  # {gateway_topic}/groups
TOPIC_DISCOVERY_SCENES = f"{{prefix}}/{TOPIC_SCENES}"  # {gateway_topic}/scenes

# Control topics (SEND - Publish)
# Note: Operation IDs (like setDevicePower, getDevicePower) are for API lookup only, not used in topics
# SET operations use property name directly (e.g., "power", "lightness")
# GET operations use property name + "Get" (e.g., "powerGet", "lightnessGet")
# Format: {gateway_topic}/lights/{device_name}/{topic_name}
TOPIC_SET_DEVICE_POWER = "{prefix}/lights/{device_name}/power"  # Operation ID: setDevicePower
TOPIC_GET_DEVICE_POWER = "{prefix}/lights/{device_name}/powerGet"  # Operation ID: getDevicePower
TOPIC_SET_DEVICE_LIGHTNESS = "{prefix}/lights/{device_name}/lightness"  # Operation ID: setDeviceLightness
TOPIC_GET_DEVICE_LIGHTNESS = "{prefix}/lights/{device_name}/lightnessGet"  # Operation ID: getDeviceLightness
TOPIC_SET_DEVICE_TEMPERATURE = "{prefix}/lights/{device_name}/temperature"  # Operation ID: setDeviceTemperature <-- Not working!! use ctl 01.2026
TOPIC_SET_DEVICE_CTL = "{prefix}/lights/{device_name}/ctl"  # Operation ID: setDeviceCtl
TOPIC_GET_DEVICE_CTL = "{prefix}/lights/{device_name}/ctlGet"  # Operation ID: getDeviceCtl
TOPIC_SET_GROUP_POWER = "{prefix}/groups/{group_name}/power"  # Operation ID: setGroupPower
TOPIC_GET_GROUP_POWER = "{prefix}/groups/{group_name}/powerGet"  # Operation ID: getGroupPower
TOPIC_SET_GROUP_LIGHTNESS = "{prefix}/groups/{group_name}/lightness"  # Operation ID: setGroupLightness
TOPIC_GET_GROUP_LIGHTNESS = "{prefix}/groups/{group_name}/lightnessGet"  # Operation ID: getGroupLightness
TOPIC_SCENE_ACTIVATE = "{prefix}/scenes/{scene_name}/activate"  # Operation ID: recallScene

# Status topics (RECEIVE - Subscribe)
# API: RECEIVE lightStatus, groupStatus
# Format: {gateway_topic}/lights/{device_name}/status
TOPIC_DEVICE_STATUS = "{prefix}/lights/{device_name}/status"  # lightStatus
TOPIC_GROUP_STATUS = "{prefix}/groups/{group_name}/status"  # groupStatus (Operation ID: groupStatus)

# Configuration keys
CONF_TOPIC_PREFIX = "topic_prefix"
CONF_POLLING_INTERVAL = "polling_interval"
CONF_POLLING_TIMEOUT = "polling_timeout"
CONF_POLLING_MODE = "polling_mode"
CONF_ENABLE_GROUPS = "enable_groups"
CONF_ENABLE_SCENES = "enable_scenes"

# Polling modes
POLLING_MODE_NORMAL = "normal"  # Each device polls independently
POLLING_MODE_ROTATIONAL = "rotational"  # One device at a time in rotation - use at big networks (>5 lights)
DEFAULT_POLLING_MODE = POLLING_MODE_NORMAL

# MQTT Broker Configuration (optional - uses HA MQTT if not provided)
CONF_MQTT_BROKER = "mqtt_broker"
CONF_MQTT_PORT = "mqtt_port"
CONF_MQTT_USERNAME = "mqtt_username"
CONF_MQTT_PASSWORD = "mqtt_password"
CONF_USE_HA_MQTT = "use_ha_mqtt"  # Use Home Assistant's MQTT integration

# Default MQTT broker settings
DEFAULT_MQTT_PORT = 1883

# Event names
EVENT_DEVICES_UPDATED = "hafele_local_mqtt_devices_updated"

