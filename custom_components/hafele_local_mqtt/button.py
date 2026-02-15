"""Button platform for Hafele Local MQTT."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    EVENT_DEVICES_UPDATED,
    TOPIC_GET_DEVICE_LIGHTNESS,
    TOPIC_GET_DEVICE_POWER,
    TOPIC_GET_DEVICE_CTL,
)
from .discovery import HafeleDiscovery
from .mqtt_client import HafeleMQTTClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hafele buttons from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    mqtt_client: HafeleMQTTClient = data["mqtt_client"]
    discovery: HafeleDiscovery = data["discovery"]
    topic_prefix = data["topic_prefix"]

    # Track which entities we've already created in this session
    created_entities: set[tuple[int, str]] = set()  # (device_addr, button_type)
    
    # Get entity registry to check for existing entities
    entity_registry = er.async_get(hass)

    async def _create_entities_for_devices() -> None:
        """Create button entities for all discovered light devices."""
        devices = discovery.get_all_devices()
        new_entities = []

        for device_addr, device_info in devices.items():
            device_name = device_info.get("device_name", f"device_{device_addr}")
            
            # Only create buttons for light devices
            # Check device_types to ensure this is a light (not a switch, etc.)
            device_types = device_info.get("device_types", [])
            # device_types can contain: "light", "multiwhite", "rgb" (case may vary)
            # If device_types exists, check if it contains any light-related type
            if device_types:
                # Check if this is a light type device (case-insensitive check)
                device_types_lower = [dt.lower() for dt in device_types if isinstance(dt, str)]
                is_light_device = any(
                    dtype in ["light", "multiwhite", "rgb"] 
                    for dtype in device_types_lower
                )
                if not is_light_device:
                    _LOGGER.debug(
                        "Skipping button creation for device %s (addr: %s) - not a light type (types: %s)",
                        device_name,
                        device_addr,
                        device_types,
                    )
                    continue
            
            # Create "Ping lightness" button
            lightness_button_id = (device_addr, "lightness")
            if lightness_button_id not in created_entities:
                unique_id = f"{device_addr}_ping_lightness"
                existing_entity_id = entity_registry.async_get_entity_id(
                    "button", DOMAIN, unique_id
                )
                if existing_entity_id:
                    _LOGGER.debug(
                        "Button entity already exists for device %s lightness (entity_id: %s), restoring",
                        device_addr,
                        existing_entity_id,
                    )
                
                entity = HafelePingButton(
                    mqtt_client,
                    device_addr,
                    device_info,
                    device_name,
                    topic_prefix,
                    "lightness",
                    "Ping lightness",
                    unique_id,
                )
                new_entities.append(entity)
                created_entities.add(lightness_button_id)
            
            # Create "Ping power" button
            power_button_id = (device_addr, "power")
            if power_button_id not in created_entities:
                unique_id = f"{device_addr}_ping_power"
                existing_entity_id = entity_registry.async_get_entity_id(
                    "button", DOMAIN, unique_id
                )
                if existing_entity_id:
                    _LOGGER.debug(
                        "Button entity already exists for device %s power (entity_id: %s), restoring",
                        device_addr,
                        existing_entity_id,
                    )
                
                entity = HafelePingButton(
                    mqtt_client,
                    device_addr,
                    device_info,
                    device_name,
                    topic_prefix,
                    "power",
                    "Ping power",
                    unique_id,
                )
                new_entities.append(entity)
                created_entities.add(power_button_id)

        if new_entities:
            _LOGGER.info("Adding %d button entities", len(new_entities))
            # Register entities in registry with suggested entity_id before adding
            import re
            for entity in new_entities:
                device_name = entity.device_info.get("device_name", f"device_{entity.device_addr}")
                # Generate entity_id from device name: lowercase, replace spaces with underscores
                entity_id_base = device_name.lower().replace(" ", "_").replace("-", "_")
                # Remove any special characters that aren't allowed in entity IDs
                entity_id_base = re.sub(r"[^a-z0-9_]", "", entity_id_base)
                suggested_object_id = f"{entity_id_base}_{entity.button_type}_ping"
                
                # Register/update entity in registry with suggested entity_id
                entity_registry.async_get_or_create(
                    "button",
                    DOMAIN,
                    entity.unique_id,
                    suggested_object_id=suggested_object_id,
                )
            
            # Add all entities - Home Assistant will handle duplicates gracefully
            async_add_entities(new_entities, update_before_add=False)

    @callback
    def _on_devices_updated(event) -> None:
        """Handle device discovery update event."""
        hass.async_create_task(_create_entities_for_devices())

    # Listen for device discovery updates
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_DEVICES_UPDATED, _on_devices_updated)
    )

    # Create entities for any devices already discovered
    await _create_entities_for_devices()


class HafelePingButton(ButtonEntity):
    """Representation of a Hafele ping button."""

    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        mqtt_client: HafeleMQTTClient,
        device_addr: int,
        device_info: dict[str, Any],
        device_name: str,
        topic_prefix: str,
        button_type: str,  # "lightness" or "power"
        button_name: str,
        unique_id: str,
    ) -> None:
        """Initialize the button."""
        self.mqtt_client = mqtt_client
        self.device_addr = device_addr
        self.device_info = device_info
        self.device_name = device_name
        self.topic_prefix = topic_prefix
        self.button_type = button_type
        self._attr_unique_id = unique_id
        self._attr_name = button_name
        self._attr_has_entity_name = True

        # Device info - link to the light device
        # Use the same identifier format as the light entity
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_addr))},
            name=device_name,
            manufacturer="Hafele",
            model="Local MQTT Light",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        if self.button_type == "lightness":
            # Check if device is multiwhite/RGB by checking device_info
            device_types = self.device_info.get("device_types", [])
            is_multiwhite = any(
                isinstance(dt, str) and dt.lower() in ("multiwhite", "rgb")
                for dt in device_types
            )
            
            if is_multiwhite:
                # Multiwhite/RGB devices use CTL topic
                topic = TOPIC_GET_DEVICE_CTL.format(
                    prefix=self.topic_prefix, device_name=self.device_name
                )
                _LOGGER.debug("Ping lightness button pressed for Multiwhite or RGB device %s", self.device_addr)
            else:
                # Monochrome devices use lightness topic
                topic = TOPIC_GET_DEVICE_LIGHTNESS.format(
                    prefix=self.topic_prefix, device_name=self.device_name
                )
                _LOGGER.debug("Ping lightness button pressed for Monochrome device %s", self.device_addr)
        elif self.button_type == "power":
            topic = TOPIC_GET_DEVICE_POWER.format(
                prefix=self.topic_prefix, device_name=self.device_name
            )
            _LOGGER.debug("Ping power button pressed for device %s", self.device_addr)
        else:
            _LOGGER.error("Unknown button type: %s", self.button_type)
            return

        # Publish empty payload to request status
        await self.mqtt_client.async_publish(topic, {}, qos=1)
        _LOGGER.info("Sent %s get request for device %s", self.button_type, self.device_addr)

