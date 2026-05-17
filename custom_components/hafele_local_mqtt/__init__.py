"""The Hafele Local MQTT integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_MQTT_BROKER,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_POLLING_MODE,
    CONF_USE_HA_MQTT,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_POLLING_MODE,
    DEFAULT_POLLING_TIMEOUT,
    DOMAIN,
)
from .mqtt_client import HafeleMQTTClient
from .discovery import HafeleDiscovery

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.BUTTON]


def _entry_uses_ha_mqtt(entry: ConfigEntry) -> bool:
    """Return True when the integration should use Home Assistant's MQTT broker."""
    if CONF_USE_HA_MQTT in entry.data:
        return bool(entry.data[CONF_USE_HA_MQTT])
    # Legacy entries: broker host implies a direct connection
    return not entry.data.get(CONF_MQTT_BROKER)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry data and light entity unique IDs."""
    if entry.version < 2:
        new_data = dict(entry.data)
        if new_data.get(CONF_MQTT_BROKER) and CONF_USE_HA_MQTT not in new_data:
            new_data[CONF_USE_HA_MQTT] = False
        hass.config_entries.async_update_entry(entry, data=new_data, version=2)

    ent_reg = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        uid = entity.unique_id
        if (
            not uid
            or entity.platform != DOMAIN
            or not uid.endswith("_mqtt")
            or uid.startswith("hafele_")
        ):
            continue
        addr_part = uid[: -len("_mqtt")]
        if not addr_part.isdigit():
            continue
        new_uid = f"hafele_{addr_part}"
        if ent_reg.async_get_entity_id(entity.domain, DOMAIN, new_uid):
            _LOGGER.warning(
                "Skipping unique_id migration for %s: %s already registered",
                entity.entity_id,
                new_uid,
            )
            continue
        _LOGGER.info("Migrating %s unique_id %s -> %s", entity.entity_id, uid, new_uid)
        ent_reg.async_update_entity(entity.entity_id, new_unique_id=new_uid)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hafele Local MQTT from a config entry."""
    _LOGGER.info("Setting up Hafele Local MQTT integration")

    # Get configuration
    topic_prefix = entry.data.get("topic_prefix", "hafele")
    polling_interval = entry.data.get("polling_interval", DEFAULT_POLLING_INTERVAL)
    polling_timeout = entry.data.get("polling_timeout", DEFAULT_POLLING_TIMEOUT)
    polling_mode = entry.data.get(CONF_POLLING_MODE, DEFAULT_POLLING_MODE)
    
    # Get MQTT broker configuration
    use_ha_mqtt = _entry_uses_ha_mqtt(entry)
    mqtt_broker = entry.data.get(CONF_MQTT_BROKER) if not use_ha_mqtt else None
    mqtt_port = entry.data.get(CONF_MQTT_PORT, 1883) if not use_ha_mqtt else 1883
    mqtt_username = entry.data.get(CONF_MQTT_USERNAME) if not use_ha_mqtt else None
    mqtt_password = entry.data.get(CONF_MQTT_PASSWORD) if not use_ha_mqtt else None

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

