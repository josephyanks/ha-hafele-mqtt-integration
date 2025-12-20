"""Group platform for Hafele Local MQTT."""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import timedelta
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)

from .const import (
    DOMAIN,
    EVENT_DEVICES_UPDATED,
    TOPIC_GET_GROUP_LIGHTNESS,
    TOPIC_GET_GROUP_POWER,
    TOPIC_SET_GROUP_LIGHTNESS,
    TOPIC_SET_GROUP_POWER,
    TOPIC_GROUP_STATUS,
)
from .discovery import HafeleDiscovery
from .mqtt_client import HafeleMQTTClient

_LOGGER = logging.getLogger(__name__)


class HafeleGroupCoordinator(DataUpdateCoordinator):
    """Coordinator for polling Hafele group status."""

    def __init__(
        self,
        hass: HomeAssistant,
        mqtt_client: HafeleMQTTClient,
        group_addr: int,
        group_name: str,
        topic_prefix: str,
        polling_interval: int,
        polling_timeout: int,
    ) -> None:
        """Initialize the coordinator."""
        self.mqtt_client = mqtt_client
        self.group_addr = group_addr
        self.group_name = group_name
        self.topic_prefix = topic_prefix
        self.polling_timeout = polling_timeout
        self._status_data: dict[str, Any] = {}
        self._status_received = False
        self._unsubscribers: list = []

        # Subscribe to group-specific status topic (use group name as-is, no encoding)
        status_topic = TOPIC_GROUP_STATUS.format(
            prefix=topic_prefix, group_name=group_name
        )

        _LOGGER.debug(
            "Setting up status subscription for group %s (name: %s) on topic: %s",
            group_addr,
            group_name,
            status_topic,
        )

        # Group-specific status topic
        self.response_topics = [status_topic]
        self._group_name = group_name

        super().__init__(
            hass,
            _LOGGER,
            name=f"hafele_group_{group_addr}",
            update_interval=timedelta(seconds=polling_interval),
        )

    async def _async_setup_subscriptions(self) -> None:
        """Set up MQTT subscriptions for status responses."""
        for topic in self.response_topics:
            unsub = await self.mqtt_client.async_subscribe(
                topic, self._on_status_message
            )
            if unsub:
                self._unsubscribers.append(unsub)

    async def _async_shutdown(self) -> None:
        """Clean up subscriptions."""
        for unsub in self._unsubscribers:
            if callable(unsub):
                unsub()
        self._unsubscribers.clear()
        await super()._async_shutdown()

    @callback
    def _on_status_message(self, topic: str, payload: Any) -> None:
        """Handle status response message."""
        try:
            if isinstance(payload, str):
                data = json.loads(payload)
            else:
                data = payload

            # Merge new status data with existing data
            if isinstance(data, dict) and isinstance(self._status_data, dict):
                self._status_data.update(data)
                merged_data = self._status_data
            else:
                self._status_data = data
                merged_data = data

            self._status_received = True
            _LOGGER.debug(
                "Received status for group %s (name: %s): %s (merged: %s)",
                self.group_addr,
                self.group_name,
                data,
                merged_data,
            )
            self.async_set_updated_data(merged_data)

        except (json.JSONDecodeError, TypeError) as err:
            _LOGGER.error(
                "Error parsing status message for group %s: %s",
                self.group_addr,
                err,
            )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch status from group via MQTT polling."""
        import asyncio

        # Request status using getGroupPower and getGroupLightness operations
        get_power_topic = TOPIC_GET_GROUP_POWER.format(
            prefix=self.topic_prefix, group_name=self._group_name
        )
        get_lightness_topic = TOPIC_GET_GROUP_LIGHTNESS.format(
            prefix=self.topic_prefix, group_name=self._group_name
        )

        _LOGGER.debug(
            "Requesting status for group %s (name: %s) on topics: %s, %s",
            self.group_addr,
            self.group_name,
            get_power_topic,
            get_lightness_topic,
        )

        # Reset status received flag
        self._status_received = False
        old_data = self._status_data.copy() if isinstance(self._status_data, dict) else {}

        # Request both power and lightness status
        await self.mqtt_client.async_publish(get_power_topic, {}, qos=1)
        await self.mqtt_client.async_publish(get_lightness_topic, {}, qos=1)

        # Wait for response (with timeout)
        timeout = self.polling_timeout
        elapsed = 0
        while not self._status_received and elapsed < timeout:
            await asyncio.sleep(0.1)
            elapsed += 0.1

        if not self._status_received:
            _LOGGER.warning(
                "Timeout waiting for status response from group %s",
                self.group_addr,
            )
            return old_data if old_data else {}

        return self._status_data if isinstance(self._status_data, dict) else {}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hafele groups from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    mqtt_client: HafeleMQTTClient = data["mqtt_client"]
    discovery: HafeleDiscovery = data["discovery"]
    topic_prefix = data["topic_prefix"]
    polling_interval = data["polling_interval"]
    polling_timeout = data["polling_timeout"]

    # Track which entities we've already created in this session
    created_entities: set[int] = set()
    
    # Get entity registry to check for existing entities
    entity_registry = er.async_get(hass)

    async def _create_entities_for_groups() -> None:
        """Create entities for all discovered groups."""
        groups = discovery.get_all_groups()
        new_entities = []

        for group_addr, group_info in groups.items():
            # Skip if we've already created this entity in this session
            if group_addr in created_entities:
                continue
            
            # Check if entity already exists in Home Assistant's entity registry
            unique_id = f"{group_addr}_mqtt_group"
            existing_entity_id = entity_registry.async_get_entity_id(
                "light", DOMAIN, unique_id
            )
            if existing_entity_id:
                _LOGGER.debug(
                    "Group entity already exists for group %s (addr: %s, entity_id: %s), restoring",
                    group_info.get("group_name"),
                    group_addr,
                    existing_entity_id,
                )
                # Continue to create the entity - Home Assistant will use the existing registry entry

            group_name = group_info.get("group_name", f"group_{group_addr}")
            
            # Special case for TOS_Internal_All - use friendly name
            display_name = "All hafele lights" if group_name == "TOS_Internal_All" else group_name

            _LOGGER.info(
                "Creating group entity for group: %s (addr: %s)",
                display_name,
                group_addr,
            )

            # Create coordinator for this group
            coordinator = HafeleGroupCoordinator(
                hass,
                mqtt_client,
                group_addr,
                group_name,
                topic_prefix,
                polling_interval,
                polling_timeout,
            )

            # Set up subscriptions to group status topic
            await coordinator._async_setup_subscriptions()
            
            # Start individual coordinator polling
            await coordinator.async_request_refresh()

            # Create entity
            entity = HafeleGroupEntity(
                coordinator, group_addr, group_info, group_name, display_name, mqtt_client, topic_prefix
            )
            
            new_entities.append(entity)
            created_entities.add(group_addr)

        if new_entities:
            _LOGGER.info("Adding %d group entities", len(new_entities))
            # Register entities in registry with suggested entity_id before adding
            import re
            for entity in new_entities:
                # Generate entity_id from display name: lowercase, replace spaces with underscores
                entity_id_base = entity.display_name.lower().replace(" ", "_").replace("-", "_")
                # Remove any special characters that aren't allowed in entity IDs
                entity_id_base = re.sub(r"[^a-z0-9_]", "", entity_id_base)
                suggested_object_id = f"{entity_id_base}_mqtt_group"
                
                # Register/update entity in registry with suggested entity_id
                entity_registry.async_get_or_create(
                    "light",
                    DOMAIN,
                    entity.unique_id,
                    suggested_object_id=suggested_object_id,
                )
            
            # Add all entities - Home Assistant will handle duplicates gracefully
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


class HafeleGroupEntity(CoordinatorEntity, LightEntity):
    """Representation of a Hafele group."""

    def __init__(
        self,
        coordinator: HafeleGroupCoordinator,
        group_addr: int,
        group_info: dict[str, Any],
        group_name: str,
        display_name: str,
        mqtt_client: HafeleMQTTClient,
        topic_prefix: str,
    ) -> None:
        """Initialize the group."""
        super().__init__(coordinator)
        self.group_addr = group_addr
        self.group_info = group_info
        self.group_name = group_name
        self.display_name = display_name
        self.mqtt_client = mqtt_client
        self.topic_prefix = topic_prefix
        self._attr_unique_id = f"{group_addr}_mqtt_group"
        self._attr_name = display_name
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._attr_color_mode = ColorMode.BRIGHTNESS

        # Store group name (use as-is, no encoding)
        self._group_name = group_name

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"group_{group_addr}")},
            name=self._attr_name,
            manufacturer="Hafele",
            model="Local MQTT Group",
        )

    @property
    def is_on(self) -> bool:
        """Return if the group is on."""
        if not self.coordinator.data:
            return False

        status = self.coordinator.data
        if isinstance(status, dict):
            # Check for "onoff" (lowercase, numeric response format)
            onoff = status.get("onoff")
            if onoff is not None:
                return bool(onoff) if isinstance(onoff, (int, float)) else onoff in ("on", "ON", True, 1, "1")
            
            # Check for "onOff" (camelCase, string format)
            on_off = status.get("onOff")
            if on_off is not None:
                if isinstance(on_off, (int, float)):
                    return bool(on_off)
                return on_off in ("on", "ON", True, 1, "1")
            
            # Fallback to other common formats
            power = status.get("power")
            if power is not None:
                if isinstance(power, (int, float)):
                    return bool(power)
                return power in ("on", "ON", True, 1, "1")

        return False

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the group."""
        if not self.coordinator.data:
            return None

        status = self.coordinator.data
        if isinstance(status, dict):
            # API uses "lightness" field with 0-1 scale
            lightness = status.get("lightness")
            if lightness is not None:
                # Convert from 0-1 scale to 0-255 for Home Assistant
                if isinstance(lightness, (int, float)):
                    return int(lightness * 255)

        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the group on."""
        power_topic = TOPIC_SET_GROUP_POWER.format(
            prefix=self.topic_prefix, group_name=self._group_name
        )

        # API expects boolean true/false directly, not a JSON object
        power_command = True

        # Add brightness if specified
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            # Convert to 0-1 scale (API uses 0-1 for lightness)
            lightness_value = brightness / 255.0
            # Round to 2 decimal places, rounding up
            lightness_value = math.ceil(lightness_value * 100) / 100.0
            
            # Set power first
            await self.mqtt_client.async_publish(power_topic, power_command, qos=1)
            
            # Then set brightness using group-specific lightness topic
            lightness_topic = TOPIC_SET_GROUP_LIGHTNESS.format(
                prefix=self.topic_prefix, group_name=self._group_name
            )
            lightness_command = {"lightness": lightness_value}
            await self.mqtt_client.async_publish(lightness_topic, lightness_command, qos=1)
            
            # Optimistically update state with both power and lightness values we just set
            if self.coordinator.data:
                self.coordinator.data.update({"onoff": 1, "lightness": lightness_value})
            else:
                self.coordinator.data = {"onoff": 1, "lightness": lightness_value}
            
            # Schedule a lightnessGet request 5 seconds after setting to get final value after ramping
            async def _request_lightness_after_ramp() -> None:
                await asyncio.sleep(5.0)  # Wait 5 seconds for ramping to complete
                get_lightness_topic = TOPIC_GET_GROUP_LIGHTNESS.format(
                    prefix=self.topic_prefix, group_name=self._group_name
                )
                await self.mqtt_client.async_publish(get_lightness_topic, {}, qos=1)
            
            hass = self.coordinator.hass
            hass.async_create_task(_request_lightness_after_ramp())
        else:
            await self.mqtt_client.async_publish(power_topic, power_command, qos=1)
            
            # Optimistically update state with power value we just set
            if self.coordinator.data:
                self.coordinator.data.update({"onoff": 1})
            else:
                self.coordinator.data = {"onoff": 1}
            
            # Schedule a powerGet request 5 seconds after setting to get final value after ramping
            async def _request_power_after_ramp() -> None:
                await asyncio.sleep(5.0)  # Wait 5 seconds for ramping to complete
                get_power_topic = TOPIC_GET_GROUP_POWER.format(
                    prefix=self.topic_prefix, group_name=self._group_name
                )
                await self.mqtt_client.async_publish(get_power_topic, {}, qos=1)
                # Also request lightness status
                get_lightness_topic = TOPIC_GET_GROUP_LIGHTNESS.format(
                    prefix=self.topic_prefix, group_name=self._group_name
                )
                await self.mqtt_client.async_publish(get_lightness_topic, {}, qos=1)
            
            hass = self.coordinator.hass
            hass.async_create_task(_request_power_after_ramp())

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the group off."""
        power_topic = TOPIC_SET_GROUP_POWER.format(
            prefix=self.topic_prefix, group_name=self._group_name
        )

        # API expects boolean true/false directly, not a JSON object
        power_command = False

        await self.mqtt_client.async_publish(power_topic, power_command, qos=1)

        # Optimistically update state with power value we just set
        if self.coordinator.data:
            self.coordinator.data.update({"onoff": 0})
        else:
            self.coordinator.data = {"onoff": 0}

        self.async_write_ha_state()

        # Schedule a powerGet request 5 seconds after setting to get final value after ramping
        async def _request_power_after_ramp() -> None:
            await asyncio.sleep(5.0)  # Wait 5 seconds for ramping to complete
            get_power_topic = TOPIC_GET_GROUP_POWER.format(
                prefix=self.topic_prefix, group_name=self._group_name
            )
            await self.mqtt_client.async_publish(get_power_topic, {}, qos=1)
        
        hass = self.coordinator.hass
        hass.async_create_task(_request_power_after_ramp())

