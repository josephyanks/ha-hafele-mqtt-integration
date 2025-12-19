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

# Control topics (published) - patterns to be determined
TOPIC_DEVICE_SET = "{prefix}/device/{addr}/set"
TOPIC_DEVICE_GET = "{prefix}/device/{addr}/get"
TOPIC_GROUP_SET = "{prefix}/group/{addr}/set"
TOPIC_SCENE_ACTIVATE = "{prefix}/scene/{scene_id}/activate"

# Status topics (subscribed) - patterns to be determined
TOPIC_DEVICE_STATUS = "{prefix}/device/{addr}/status"
TOPIC_DEVICE_RESPONSE = "{prefix}/device/{addr}/response"

# Configuration keys
CONF_TOPIC_PREFIX = "topic_prefix"
CONF_POLLING_INTERVAL = "polling_interval"
CONF_POLLING_TIMEOUT = "polling_timeout"
CONF_ENABLE_GROUPS = "enable_groups"
CONF_ENABLE_SCENES = "enable_scenes"

