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

# MQTT Topic Patterns (to be verified with actual API)
# Discovery topics (subscribed)
TOPIC_DISCOVERY_LIGHTS = f"{DEFAULT_TOPIC_PREFIX}/{TOPIC_LIGHTS}"
TOPIC_DISCOVERY_GROUPS = f"{DEFAULT_TOPIC_PREFIX}/{TOPIC_GROUPS}"
TOPIC_DISCOVERY_SCENES = f"{DEFAULT_TOPIC_PREFIX}/{TOPIC_SCENES}"

# Control topics (published) - operation-specific topics per API docs
# Device name is in the payload, not the topic path
TOPIC_GET_DEVICE_POWER = "{prefix}/getDevicePower"
TOPIC_SET_DEVICE_POWER = "{prefix}/setDevicePower"
TOPIC_SET_DEVICE_LIGHTNESS = "{prefix}/setDeviceLightness"
TOPIC_GET_DEVICE_LIGHTNESS = "{prefix}/getDeviceLightness"
TOPIC_SET_GROUP_POWER = "{prefix}/setGroupPower"
TOPIC_GET_GROUP_POWER = "{prefix}/getGroupPower"
TOPIC_RECALL_SCENE = "{prefix}/recallScene"

# Status topics (subscribed) - operation-specific topics per API docs
TOPIC_LIGHT_STATUS = "{prefix}/lightStatus"
TOPIC_GROUP_STATUS = "{prefix}/groupStatus"

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

