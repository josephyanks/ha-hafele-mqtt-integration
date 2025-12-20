"""Group light entity creation for Hafele Local MQTT groups."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_DEVICES_UPDATED
from .discovery import HafeleDiscovery

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hafele group lights from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    discovery: HafeleDiscovery = data["discovery"]

    # Track which entities we've already created in this session
    created_entities: set[int] = set()
    
    # Get entity registry to check for existing entities
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    async def _create_entities_for_groups() -> None:
        """Create light entities for all discovered groups."""
        groups = discovery.get_all_groups()
        new_entities = []

        for group_addr, group_info in groups.items():
            # Skip if we've already created this entity in this session
            if group_addr in created_entities:
                continue
            
            # Check if entity already exists
            unique_id = f"{group_addr}_group_light"
            existing_entity_id = entity_registry.async_get_entity_id(
                "light", DOMAIN, unique_id
            )
            if existing_entity_id:
                _LOGGER.debug(
                    "Group light entity already exists for group %s (addr: %s, entity_id: %s), restoring",
                    group_info.get("group_name"),
                    group_addr,
                    existing_entity_id,
                )
            
            group_name = group_info.get("group_name", f"group_{group_addr}")
            
            # Special case for TOS_Internal_All - use friendly name
            if group_name == "TOS_Internal_All":
                display_name = "All hafele lights"
            else:
                display_name = f"{group_name} group"
            
            # Get device addresses for this group
            device_addrs = group_info.get("devices", [])
            if not device_addrs:
                _LOGGER.debug(
                    "Skipping group %s - no devices",
                    group_name,
                )
                continue
            
            # Map device addresses to entity IDs
            light_entity_ids = []
            for device_addr in device_addrs:
                device_unique_id = f"{device_addr}_mqtt"
                entity_id = entity_registry.async_get_entity_id("light", DOMAIN, device_unique_id)
                if entity_id:
                    light_entity_ids.append(entity_id)
            
            if not light_entity_ids:
                _LOGGER.debug(
                    "Skipping group %s - no valid light entities found",
                    group_name,
                )
                continue
            
            _LOGGER.info(
                "Creating group light entity for group: %s (addr: %s) with %d lights",
                display_name,
                group_addr,
                len(light_entity_ids),
            )

            # Create group device
            group_device = device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"group_{group_addr}")},
                name=display_name,
                manufacturer="Hafele",
                model="Local MQTT Light Group",
            )

            # Create entity
            entity = HafeleGroupLightEntity(
                hass, group_addr, group_info, display_name, light_entity_ids, group_device.id
            )
            
            new_entities.append(entity)
            created_entities.add(group_addr)
            
            # Link individual light entities to the group device
            # This makes them appear under the group device in Home Assistant
            for device_addr in device_addrs:
                device_unique_id = f"{device_addr}_mqtt"
                light_entity_id = entity_registry.async_get_entity_id("light", DOMAIN, device_unique_id)
                if light_entity_id:
                    entity_entry = entity_registry.async_get(light_entity_id)
                    if entity_entry and entity_entry.device_id != group_device.id:
                        # Update the entity to link it to the group device
                        entity_registry.async_update_entity(
                            light_entity_id,
                            device_id=group_device.id,
                        )
                        _LOGGER.debug(
                            "Linked light entity %s to group device %s",
                            light_entity_id,
                            group_device.id,
                        )

        if new_entities:
            _LOGGER.info("Adding %d group light entities", len(new_entities))
            # Register entities in registry with suggested entity_id before adding
            import re
            for entity in new_entities:
                # Generate entity_id from display name
                entity_id_base = entity._attr_name.lower().replace(" ", "_").replace("-", "_")
                entity_id_base = re.sub(r"[^a-z0-9_]", "", entity_id_base)
                suggested_object_id = f"{entity_id_base}"
                
                # Register/update entity in registry
                entity_registry.async_get_or_create(
                    "light",
                    DOMAIN,
                    entity.unique_id,
                    suggested_object_id=suggested_object_id,
                )
            
            async_add_entities(new_entities, update_before_add=False)

    @callback
    def _on_groups_updated(event) -> None:
        """Handle group discovery update event."""
        hass.async_create_task(_create_entities_for_groups())

    # Listen for device discovery updates (groups are also included in this event)
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_DEVICES_UPDATED, _on_groups_updated)
    )

    # Create entities for any groups already discovered
    await _create_entities_for_groups()


class HafeleGroupLightEntity(LightEntity):
    """Representation of a Hafele group as a light entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        group_addr: int,
        group_info: dict[str, Any],
        display_name: str,
        light_entity_ids: list[str],
        group_device_id: str,
    ) -> None:
        """Initialize the group light."""
        self.hass = hass
        self.group_addr = group_addr
        self.group_info = group_info
        self.light_entity_ids = light_entity_ids
        self._attr_unique_id = f"{group_addr}_group_light"
        self._attr_name = display_name
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._attr_color_mode = ColorMode.BRIGHTNESS
        
        # Device info - this creates a device that contains the individual lights
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"group_{group_addr}")},
            name=display_name,
            manufacturer="Hafele",
            model="Local MQTT Light Group",
        )
        
        # Track state of individual lights for aggregation
        self._light_states: dict[str, dict[str, Any]] = {}
        
        # Listen to state changes of child lights
        self._async_unsub_state_changed = None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # Subscribe to state changes of all child lights
        @callback
        def _async_state_changed_listener(entity_id: str, old_state: Any, new_state: Any) -> None:
            """Handle child light state changes."""
            if new_state is None:
                return
            
            # Store the state
            self._light_states[entity_id] = {
                "state": new_state.state,
                "brightness": new_state.attributes.get("brightness"),
            }
            
            # Update our aggregated state
            self.async_write_ha_state()
        
        # Listen to all child light state changes
        self._async_unsub_state_changed = self.hass.helpers.event.async_track_state_change(
            self.light_entity_ids, _async_state_changed_listener
        )
        
        # Get initial states
        for entity_id in self.light_entity_ids:
            state = self.hass.states.get(entity_id)
            if state:
                self._light_states[entity_id] = {
                    "state": state.state,
                    "brightness": state.attributes.get("brightness"),
                }
        
        # Write initial state
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        if self._async_unsub_state_changed:
            self._async_unsub_state_changed()
        await super().async_will_remove_from_hass()

    @property
    def is_on(self) -> bool:
        """Return if the group is on (only true if ALL lights are on)."""
        if not self._light_states or len(self._light_states) != len(self.light_entity_ids):
            return False
        
        # Check if all lights are on
        for entity_id in self.light_entity_ids:
            state_data = self._light_states.get(entity_id)
            if not state_data or state_data.get("state") != "on":
                return False
        
        return True

    @property
    def brightness(self) -> int | None:
        """Return the average brightness of all lights."""
        if not self._light_states:
            return None
        
        brightnesses = []
        for entity_id in self.light_entity_ids:
            state_data = self._light_states.get(entity_id)
            if state_data and state_data.get("state") == "on":
                brightness = state_data.get("brightness")
                if brightness is not None:
                    brightnesses.append(brightness)
        
        if not brightnesses:
            return None
        
        # Return average brightness
        return int(sum(brightnesses) / len(brightnesses))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the group on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        
        # Turn on all lights in the group
        tasks = []
        for entity_id in self.light_entity_ids:
            service_data = {"entity_id": entity_id}
            if brightness is not None:
                service_data[ATTR_BRIGHTNESS] = brightness
            tasks.append(
                self.hass.services.async_call("light", "turn_on", service_data)
            )
        
        await asyncio.gather(*tasks)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the group off."""
        # Turn off all lights in the group
        tasks = [
            self.hass.services.async_call(
                "light", "turn_off", {"entity_id": entity_id}
            )
            for entity_id in self.light_entity_ids
        ]
        
        await asyncio.gather(*tasks)
        self.async_write_ha_state()

