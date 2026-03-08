"""Button platform for Hafele Local MQTT."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_DEVICES_UPDATED
from .debugbutton import HafelePingButton
from .discovery import HafeleDiscovery
from .mqtt_client import HafeleMQTTClient

_LOGGER = logging.getLogger(__name__)


class HafeleReinitializeGroupsButton(ButtonEntity):
    """Button to reinitialize Hafele group entities."""

    _attr_has_entity_name = True
    _attr_name = "Reinitialize groups"

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._attr_unique_id = "hafele_reinitialize_groups"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Enable this management button by default."""
        return True

    async def async_press(self) -> None:
        """Handle the button press by triggering a groups refresh."""
        _LOGGER.info("Reinitialize groups button pressed - firing %s", EVENT_DEVICES_UPDATED)
        # Reuse the existing devices/groups updated event so platforms recreate entities
        self._hass.bus.async_fire(EVENT_DEVICES_UPDATED)


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
                device_types_lower = [
                    dt.lower() for dt in device_types if isinstance(dt, str)
                ]
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

        # Add the single management button for reinitializing groups
        # Do this only once; unique_id ensures registry stability across reloads
        reinit_unique_id = "hafele_reinitialize_groups"
        existing_reinit_id = entity_registry.async_get_entity_id(
            "button", DOMAIN, reinit_unique_id
        )
        if existing_reinit_id:
            _LOGGER.debug(
                "Reinitialize groups button already exists (entity_id: %s), restoring",
                existing_reinit_id,
            )
        reinit_button = HafeleReinitializeGroupsButton(hass)
        new_entities.append(reinit_button)

        if new_entities:
            _LOGGER.info("Adding %d button entities", len(new_entities))
            # Register entities in registry with suggested entity_id before adding
            import re

            for entity in new_entities:
                # HafelePingButton exposes device_info/device_addr; management button does not
                if isinstance(entity, HafelePingButton):
                    device_name = entity.device_info.get(
                        "device_name", f"device_{entity.device_addr}"
                    )
                    entity_id_base = (
                        device_name.lower().replace(" ", "_").replace("-", "_")
                    )
                    entity_id_base = re.sub(r"[^a-z0-9_]", "", entity_id_base)
                    suggested_object_id = (
                        f"{entity_id_base}_{entity.button_type}_ping"
                    )
                else:
                    # Management button: simple fixed object_id
                    suggested_object_id = "reinitialize_groups"

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

