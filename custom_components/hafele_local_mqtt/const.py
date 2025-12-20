"""Constants for the Hafele Local MQTT integration."""

DOMAIN = "hafele_local_mqtt"

# MQTT Topic Prefix
DEFAULT_TOPIC_PREFIX = "hafele"

# Discovery Topics
TOPIC_LIGHTS = "lights"
TOPIC_GROUPS = "groups"
TOPIC_SCENES = "scenes"

# Polling Configuration
DEFAULT_POLLING_INTERVAL = 30  # seconds
DEFAULT_POLLING_TIMEOUT = 5  # seconds

# MQTT Topic Patterns - Verified against API documentation
# Reference: https://help.connect-mesh.io/mqtt/index.html

# Discovery topics (RECEIVE - Subscribe)
# API: RECEIVE lightsDiscovery, groupDiscovery, sceneDiscovery
TOPIC_DISCOVERY_LIGHTS = f"{DEFAULT_TOPIC_PREFIX}/{TOPIC_LIGHTS}"  # {gateway_topic}/lights
TOPIC_DISCOVERY_GROUPS = f"{DEFAULT_TOPIC_PREFIX}/{TOPIC_GROUPS}"  # {gateway_topic}/groups
TOPIC_DISCOVERY_SCENES = f"{DEFAULT_TOPIC_PREFIX}/{TOPIC_SCENES}"  # {gateway_topic}/scenes

# Control topics (SEND - Publish)
# Note: Operation IDs (like setDevicePower, getDevicePower) are for API lookup only, not used in topics
# SET operations use property name directly (e.g., "power", "lightness")
# GET operations use property name + "Get" (e.g., "powerGet", "lightnessGet")
# Format: {gateway_topic}/lights/{device_name}/{topic_name}
TOPIC_SET_DEVICE_POWER = "{prefix}/lights/{device_name}/power"  # Operation ID: setDevicePower
TOPIC_GET_DEVICE_POWER = "{prefix}/lights/{device_name}/powerGet"  # Operation ID: getDevicePower
TOPIC_SET_DEVICE_LIGHTNESS = "{prefix}/lights/{device_name}/lightness"  # Operation ID: setDeviceLightness
TOPIC_GET_DEVICE_LIGHTNESS = "{prefix}/lights/{device_name}/lightnessGet"  # Operation ID: getDeviceLightness
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
CONF_ENABLE_GROUPS = "enable_groups"
CONF_ENABLE_SCENES = "enable_scenes"

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

