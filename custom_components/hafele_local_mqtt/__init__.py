"""The Hafele Local MQTT integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, DEFAULT_POLLING_MODE, CONF_POLLING_MODE
from .mqtt_client import HafeleMQTTClient
from .discovery import HafeleDiscovery

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hafele Local MQTT from a config entry."""
    _LOGGER.info("Setting up Hafele Local MQTT integration")

    # Get configuration
    topic_prefix = entry.data.get("topic_prefix", "hafele")
    polling_interval = entry.data.get("polling_interval", 60)
    polling_timeout = entry.data.get("polling_timeout", 5)
    polling_mode = entry.data.get(CONF_POLLING_MODE, DEFAULT_POLLING_MODE)
    
    # Get MQTT broker configuration
    use_ha_mqtt = entry.data.get("use_ha_mqtt", True)
    mqtt_broker = entry.data.get("mqtt_broker") if not use_ha_mqtt else None
    mqtt_port = entry.data.get("mqtt_port", 1883) if not use_ha_mqtt else 1883
    mqtt_username = entry.data.get("mqtt_username") if not use_ha_mqtt else None
    mqtt_password = entry.data.get("mqtt_password") if not use_ha_mqtt else None

    # Initialize MQTT client
    mqtt_client = HafeleMQTTClient(
        hass,
        topic_prefix,
        broker=mqtt_broker,
        port=mqtt_port,
        username=mqtt_username,
        password=mqtt_password,
    )
    await mqtt_client.async_connect()

    # Initialize discovery
    discovery = HafeleDiscovery(hass, mqtt_client, topic_prefix)
    await discovery.async_start()

    # Store in hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "mqtt_client": mqtt_client,
        "discovery": discovery,
        "topic_prefix": topic_prefix,
        "polling_interval": polling_interval,
        "polling_timeout": polling_timeout,
        "polling_mode": polling_mode,
    }

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Hafele Local MQTT integration")

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up
        data = hass.data[DOMAIN].pop(entry.entry_id)
        discovery = data.get("discovery")
        if discovery:
            await discovery.async_stop()
        mqtt_client = data.get("mqtt_client")
        if mqtt_client:
            await mqtt_client.async_disconnect()

    return unload_ok

