"""Light platform for Hafele Local MQTT."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import math
from datetime import timedelta
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    COLOR_MODE_COLOR_TEMP,
    ColorMode,
    LightEntity,
    ATTR_COLOR_TEMP_KELVIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    EVENT_DEVICES_UPDATED,
    TOPIC_GET_DEVICE_LIGHTNESS,
    TOPIC_GET_DEVICE_POWER,
    TOPIC_SET_DEVICE_CTL,
    TOPIC_GET_DEVICE_CTL,
    TOPIC_GET_GROUP_LIGHTNESS,
    TOPIC_GET_GROUP_POWER,
    TOPIC_SET_DEVICE_LIGHTNESS,
    TOPIC_SET_DEVICE_POWER,
    TOPIC_DEVICE_STATUS,
    DEFAULT_POLLING_MODE,
    POLLING_MODE_NORMAL,
    POLLING_MODE_ROTATIONAL,
)
from .discovery import HafeleDiscovery
from .mqtt_client import HafeleMQTTClient

_LOGGER = logging.getLogger(__name__)


class HafeleLightCoordinator(DataUpdateCoordinator):
    """Coordinator for polling Hafele light status."""

    def __init__(
        self,
        hass: HomeAssistant,
        mqtt_client: HafeleMQTTClient,
        device_addr: int,
        device_name: str,
        topic_prefix: str,
        polling_interval: int,
        polling_timeout: int,
        polling_mode: str,
    ) -> None:
        """Initialize the coordinator."""
        self.mqtt_client = mqtt_client
        self.device_addr = device_addr
        self.device_name = device_name
        self.topic_prefix = topic_prefix
        self.polling_timeout = polling_timeout
        self.polling_mode = polling_mode
        self._status_data: dict[str, Any] = {}
        self._status_received = False
        self._unsubscribers: list = []
        self.entity: HafeleLightEntity | None = None  # HaefeleLightEntity

        # Subscribe to device-specific status topic (use device name as-is, no encoding)
        status_topic = TOPIC_DEVICE_STATUS.format(
            prefix=topic_prefix, device_name=device_name
        )



        # Device-specific status topic
        self.response_topics = [status_topic]
        self._device_name = device_name

        # Set update_interval based on polling mode
        # For normal mode: each device polls independently
        # For rotational mode: no automatic polling, rotational loop handles it
        update_interval = (
            timedelta(seconds=polling_interval)
            if polling_mode == POLLING_MODE_NORMAL
            else None
        )
        _LOGGER.debug(
            "Setting up status subscription for device %s (name: %s) on topic: %s with update interval %s",
            device_addr,
            device_name,
            status_topic,
            update_interval
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"hafele_light_{device_addr}",
            update_interval=update_interval,
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
                # Handle both sync and async unsubscribe functions
                if inspect.iscoroutinefunction(unsub):
                    await unsub()
                else:
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
            if "lightness" in data:
                # also update power - if häfele lightness == 0 -> off, else on
                if data["lightness"] > 0:
                    data["onoff"] = 1
                else:
                    data["onoff"] = 0
                _LOGGER.debug(f'Updating onoff to {data["onoff"]} due to lightness {data["lightness"]}')


            # Merge new status data with existing data
            # Status responses may not include all fields, so we preserve existing values
            if isinstance(data, dict) and isinstance(self._status_data, dict):
                # Update only the fields that are present in the new status
                self._status_data.update(data)
                merged_data = self._status_data
            else:
                # If existing data isn't a dict, just use the new data
                self._status_data = data
                merged_data = data
            self._status_received = True
            _LOGGER.debug(
                "Received status for device %s (name: %s): %s (merged: %s)",
                self.device_addr,
                self.device_name,
                data,
                merged_data,
            )
            # Notify coordinator that data is available (send merged data)
            self.async_set_updated_data(merged_data)

        except (json.JSONDecodeError, TypeError) as err:
            _LOGGER.error(
                "Error parsing status message for device %s: %s",
                self.device_addr,
                err,
            )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch status from device via MQTT polling."""
        # Request status using getDeviceLightness operation only
        # Power state is inferred from lightness (lightness > 0 = on)
        if self.entity and self.entity.is_multiwhite:
            _type = "Multiwhite"
            get_lightness_topic = TOPIC_GET_DEVICE_CTL.format(
                prefix=self.topic_prefix, device_name=self._device_name
            )
        else:
            _type = "Monochrome"
            get_lightness_topic = TOPIC_GET_DEVICE_LIGHTNESS.format(
                prefix=self.topic_prefix, device_name=self._device_name
            )
        _LOGGER.debug(
            "Requesting lightness status for %s device %s (name: %s) on topic: %s", _type,
            self.device_addr, self.device_name, get_lightness_topic)

        # Reset status received flag
        self._status_received = False
        # Keep a copy of existing data to preserve it if no response comes
        old_data = self._status_data.copy() if isinstance(self._status_data, dict) else {}

        # Request only lightness status (power inferred from lightness)
        await self.mqtt_client.async_publish(get_lightness_topic, {}, qos=1)

        # Wait for response (with timeout)
        # Note: We wait for at least one status update, which may contain partial data
        timeout = self.polling_timeout
        elapsed = 0
        while not self._status_received and elapsed < timeout:
            await asyncio.sleep(0.1)
            elapsed += 0.1

        if not self._status_received:
            _LOGGER.warning(
                "Timeout waiting for status response from device %s",
                self.device_addr,
            )
            # Return existing data (preserves all fields even if no new update)
            return old_data if old_data else {}

        # Return merged status data (includes both old and new fields)
        return self._status_data if isinstance(self._status_data, dict) else {}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hafele lights from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    mqtt_client: HafeleMQTTClient = data["mqtt_client"]
    discovery: HafeleDiscovery = data["discovery"]
    topic_prefix = data["topic_prefix"]
    polling_interval = data["polling_interval"]
    polling_timeout = data["polling_timeout"]
    polling_mode = data.get("polling_mode", DEFAULT_POLLING_MODE)
    _LOGGER.debug(f"async_setup_entry: topic_prefix {topic_prefix}, polling mode: {polling_mode},"
                  f" polling interval {polling_interval}")

    # Track which entities we've already created in this session
    created_entities: set[int] = set()
    
    # Track coordinators for startup status requests
    coordinators: dict[int, HafeleLightCoordinator] = {}
    
    # Get entity registry to check for existing entities
    entity_registry = er.async_get(hass)

    async def _create_entities_for_devices() -> None:
        """Create entities for all discovered light devices."""
        devices = discovery.get_all_devices()
        new_entities = []

        for device_addr, device_info in devices.items():
            # Skip if we've already created this entity in this session
            if device_addr in created_entities:
                continue
            
            # Check if entity already exists in Home Assistant's entity registry
            # We still need to create and provide the entity even if it exists,
            # otherwise Home Assistant will think it's no longer being provided
            unique_id = f"{device_addr}_mqtt"
            existing_entity_id = entity_registry.async_get_entity_id(
                "light", DOMAIN, unique_id
            )
            if existing_entity_id:
                _LOGGER.debug(
                    "Entity already exists for device %s (addr: %s, entity_id: %s), restoring",
                    device_info.get("device_name"),
                    device_addr,
                    existing_entity_id,
                )
                # Continue to create the entity - Home Assistant will use the existing registry entry

            # Only create entities for lights
            # Since these come from the lights discovery topic, they should all be lights
            # But check device_types if it exists to be safe
            device_types = device_info.get("device_types", [])

            # Treat "Light" and "Multiwhite" as light devices
            if device_types and not any(t.lower() in ("light", "multiwhite") for t in device_types):
                _LOGGER.debug(
                    "Skipping device %s (addr: %s) - not a light type",
                    device_info.get("device_name"),
                    device_addr,
                )
                continue

            _LOGGER.info(
                "Creating light entity for device: %s (addr: %s)",
                device_info.get("device_name"),
                device_addr,
            )

            # Get device name for topic construction
            device_name = device_info.get("device_name", f"device_{device_addr}")

            # Create coordinator for this device
            coordinator = HafeleLightCoordinator(
                hass,
                mqtt_client,
                device_addr,
                device_name,
                topic_prefix,
                polling_interval,
                polling_timeout,
                polling_mode,
            )

            # Set up subscriptions to device status topic
            await coordinator._async_setup_subscriptions()
            

            # Start individual coordinator polling
            # Use async_request_refresh instead of async_config_entry_first_refresh
            # since we don't have a config entry reference in the coordinator
            # don't refresh at the start - otherwise the BLE Network gets spammed
            # polling will update it later
            # await coordinator.async_request_refresh()

            # Create entity
            entity = HafeleLightEntity(
                coordinator, device_addr, device_info, mqtt_client, topic_prefix
            )

            # Store coordinator reference for startup status tracking
            coordinator.entity = entity
            coordinators[device_addr] = coordinator

            new_entities.append(entity)
            created_entities.add(device_addr)

        if new_entities:
            _LOGGER.info("Adding %d light entities", len(new_entities))
            # Register entities in registry with suggested entity_id before adding
            # This ensures entity_id format is correct, even for existing entities
            import re
            for entity in new_entities:
                device_name = entity.device_info.get("device_name", f"device_{entity.device_addr}")
                # Generate entity_id from device name: lowercase, replace spaces with underscores
                entity_id_base = device_name.lower().replace(" ", "_").replace("-", "_")
                # Remove any special characters that aren't allowed in entity IDs
                entity_id_base = re.sub(r"[^a-z0-9_]", "", entity_id_base)
                suggested_object_id = f"{entity_id_base}_mqtt"
                
                # Register/update entity in registry with suggested entity_id
                # This will update existing entities or create new ones
                entity_registry.async_get_or_create(
                    "light",
                    DOMAIN,
                    entity.unique_id,
                    suggested_object_id=suggested_object_id,
                )
            
            # Add all entities - Home Assistant will handle duplicates gracefully
            # and restore existing entities properly
            async_add_entities(new_entities, update_before_add=False)
            _LOGGER.info("Finished adding %d light entities", len(new_entities))

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

    # Start rotational polling only if polling_mode is rotational
    # Normal mode uses per-device automatic polling via update_interval
    if polling_mode == POLLING_MODE_ROTATIONAL:
        async def _rotational_polling_loop() -> None:
            """Rotational Polling with Fine-Grained PollPriority and sleep after each update.
                - Update all HIGH priority entities first, one by one, sleeping after each update
                - Normal priority entities are updated round-robin, sleeping after each update
                - After each update, lists are rebuilt to catch new HIGH priorities
            """
            rr_index = 0  # Round-Robin index for normal entities
            _LOGGER.debug("Starting rational polling loop")
            await hass.async_block_till_done() # otherwise startup of HA is blocked
            _LOGGER.info("Homeassistant started - we start polling")
            while True:
                try:
                    high_priority_entities = []
                    normal_entities = []

                    # Single pass: collect entities and split by priority
                    for c in coordinators.values():
                        entity = c.entity
                        if entity is None:
                            continue
                        if entity.priority == PollPriority.HIGH:
                            high_priority_entities.append(entity)
                        else:
                            normal_entities.append(entity)
                    if not high_priority_entities and not normal_entities:
                        _LOGGER.warning("No entities found to poll")
                        await asyncio.sleep(polling_interval)
                        continue
                    # Update HIGH priority entities first
                    for entity in high_priority_entities:
                        try:
                            _LOGGER.debug(
                                "Updating HIGH priority entity: %s (%s)",
                                entity.device_name,
                                entity.device_addr,
                            )
                            await entity.coordinator.async_request_refresh()
                            entity.reset_priority()  # Optional: reset priority after update
                        except Exception as e:
                            _LOGGER.exception(
                                "Error updating HIGH priority entity %s: %s",
                                entity.device_name, e,
                            )
                        await asyncio.sleep(polling_interval)
                    # Round-robin for normal entities (after processing high-priority entities)
                    if normal_entities:
                        entity = normal_entities[rr_index % len(normal_entities)]
                        try:
                            _LOGGER.debug(
                                "Updating NORMAL priority entity: %s (%s)",
                                entity.device_name,
                                entity.device_addr,
                            )
                            await entity.coordinator.async_request_refresh()
                            rr_index += 1
                        except Exception as e:
                            _LOGGER.exception(
                                "Error updating normal entity %s: %s",
                                entity.device_name, e,
                            )
                        await asyncio.sleep(polling_interval)

                except Exception as cycle_error:
                    _LOGGER.exception(f"Critical error in polling cycle: {cycle_error}")
                    await asyncio.sleep(polling_interval)

        # Don't start rotational polling task here - otherwise HA will wait/block some minutes
        # hass.async_create_task(_rotational_polling_loop())
        # Start polling only if HA complete started, the async_setup_entry will exit clean for
        # quick startup
        @callback
        def _start_rotational_polling(event):
            hass.async_create_task(_rotational_polling_loop())
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start_rotational_polling)
        _LOGGER.info("Rotational polling mode enabled - polling one device at a time")
    else:
        _LOGGER.info("Normal polling mode enabled - each device polls independently")

class PollPriority:
    """Polling Update Priority, the lower the priority, the faster it gets updadatet"""
    NORMAL = 5  # default priority
    HIGH = 1    # high priority = updated first

class HafeleLightEntity(CoordinatorEntity, LightEntity):
    """Representation of a Hafele light."""

    def __init__(
        self,
        coordinator: HafeleLightCoordinator,
        device_addr: int,
        device_info: dict[str, Any],
        mqtt_client: HafeleMQTTClient,
        topic_prefix: str,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self.device_addr = device_addr
        self.device_info = device_info
        self.mqtt_client = mqtt_client
        self.topic_prefix = topic_prefix
        self._attr_unique_id = f"{device_addr}_mqtt"
        self._attr_name = device_info.get("device_name", f"Hafele Light {device_addr}")

        device_types = device_info.get("device_types", [])
        self._is_multiwhite = any(t.lower() == "multiwhite" for t in device_types)

        # Store device name (use as-is, no encoding)
        device_name = device_info.get("device_name", f"device_{device_addr}")
        self._device_name = device_name
        
        # Store last known lightness value (0-1 scale, as used by API)
        self._last_known_lightness: float | None = None

        self._priority = PollPriority.NORMAL  # update priority for rational polling

        # Device info
        location = device_info.get("location", "Unknown")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_addr))},
            name=self._attr_name,
            manufacturer="Hafele",
            model="Local MQTT Light",
            suggested_area=location,
        )
    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def is_multiwhite(self) -> bool:
        return self._is_multiwhite

    @property
    def priority(self) -> int:
        """Return current priority of this entity"""
        return self._priority

    def set_high_priority(self):
        """Set this entity to high priority.
        Async-safe: simple assignment in single-threaded HA event loop.
        """
        self._priority = PollPriority.HIGH

    def reset_priority(self):
        """Reset priority to NORMAL.
        Async-safe: simple assignment in HA event loop.
        """
        self._priority = PollPriority.NORMAL

    @property
    def min_color_temp_kelvin(self) -> int | None:
        if self._is_multiwhite:
            return 2700
        return None

    @property
    def max_color_temp_kelvin(self) -> int | None:
        if self._is_multiwhite:
            return 5000
        return None

    @property
    def color_mode(self) -> ColorMode | None:
        if self._is_multiwhite:
            return ColorMode.COLOR_TEMP
        return ColorMode.BRIGHTNESS

    @property
    def supported_color_modes(self) -> set[ColorMode] | None:
        if self._is_multiwhite:
         return {ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP}
        return {ColorMode.BRIGHTNESS}

    @property
    def is_on(self) -> bool | None:
        """Return if the light is on."""
        if not self.coordinator.data:
            # Return None to show unknown state until first poll completes
            return None

        # Parse status data - API uses "onoff" or "onOff" field
        # Status responses use numeric: 1 = on, 0 = off
        # Commands use string: "on" or "off"
        status = self.coordinator.data
        if isinstance(status, dict):
            # Check for "onoff" (lowercase, numeric response format)
            onoff = status.get("onoff")
            if onoff is not None:
                # Numeric format: 1 = on, 0 = off
                return bool(onoff) if isinstance(onoff, (int, float)) else onoff in ("on", "ON", True, 1, "1")
            
            # Check for "onOff" (camelCase, string format)
            on_off = status.get("onOff")
            if on_off is not None:
                # Handle both numeric (1/0) and string ("on"/"off") formats
                if isinstance(on_off, (int, float)):
                    return bool(on_off)
                return on_off in ("on", "ON", True, 1, "1")
            
            # Fallback to other common formats for compatibility
            power = status.get("power")
            if power is not None:
                if isinstance(power, (int, float)):
                    return bool(power)
                return power in ("on", "ON", True, 1, "1")
            state = status.get("state")
            if state is not None:
                if isinstance(state, (int, float)):
                    return bool(state)
                return state in ("on", "ON", True, 1, "1")

        # Return None for unknown state (no valid data found)
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color_temperature of the light."""
        if not self.coordinator.data:
            # Return None to show unknown state until first poll completes
            return None
        #_LOGGER.debug(f"color temp is calculated for: {self}")
        status = self.coordinator.data
        if isinstance(status, dict):
            temp_kelvin = status.get("temperature")
            if temp_kelvin is not None:
                return min(max(temp_kelvin, 2700), 5000)

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        if not self.coordinator.data:
            # Return None to show unknown state until first poll completes
            # Don't use last_known_lightness here to show true unknown state
            return None

        status = self.coordinator.data
        if isinstance(status, dict):
            # Multiwhite color temp
            #if getattr(self, "_is_multiwhite", False):
            #    temp_kelvin = status.get("temperature")
            #    if temp_kelvin is not None:
            #        self._attr_color_temp_kelvin = min(max(temp_kelvin, 2700), 5000)
            #        self._attr_color_mode = ColorMode.COLOR_TEMP
            # API uses "lightness" field with 0-1 scale
            lightness = status.get("lightness")
            if lightness is not None:
                # Convert from 0-1 scale to 0-255 for Home Assistant
                if isinstance(lightness, (int, float)):
                    lightness_float = float(lightness)
                    # Store last known lightness (always store when we receive a value)
                    self._last_known_lightness = lightness_float
                    return int(lightness_float * 255)
            # Fallback to other common formats for compatibility
            brightness = status.get("brightness")
            if brightness is not None:
                if isinstance(brightness, (int, float)):
                    if brightness > 255:
                        # Assume 0-100 scale
                        brightness_value = int((brightness / 100) * 255)
                    else:
                        brightness_value = int(brightness)
                    # Store last known lightness (convert to 0-1 scale)
                    self._last_known_lightness = brightness_value / 255.0
                    return brightness_value
            level = status.get("level")
            if level is not None:
                if isinstance(level, (int, float)):
                    if level > 255:
                        level_value = int((level / 100) * 255)
                    else:
                        level_value = int(level)
                    # Store last known lightness (convert to 0-1 scale)
                    self._last_known_lightness = level_value / 255.0
                    return level_value

        # If we have last known lightness, return that (even when off)
        if self._last_known_lightness is not None:
            return int(self._last_known_lightness * 255)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        # --- MULTIWHITE ---
        if self._is_multiwhite:
            _LOGGER.info(f"Multiwhite {self} turned on")
            # Brightness
            if ATTR_BRIGHTNESS in kwargs:
                brightness = kwargs[ATTR_BRIGHTNESS]
                lightness = math.ceil((brightness / 255.0) * 100) / 100.0
                self._last_known_lightness = lightness
            else:
                lightness = self._last_known_lightness or 1.0

            # Color temperature
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                self._attr_color_temp = min(max(temp_kelvin, 2700), 5000)
            else:
                self._attr_color_temp = self._attr_color_temp or 2700

            payload_ctl = {
                "lightness" : lightness,
                "temperature": self._attr_color_temp,
            }
            topic_ctl = TOPIC_SET_DEVICE_CTL.format(
                prefix=self.topic_prefix, device_name=self._device_name
            )

            await self.mqtt_client.async_publish(topic_ctl, payload_ctl, qos=1)
            # Optimistically update state
            if self.coordinator.data:
                self.coordinator.data.update(
                    {
                        "onoff": 1,
                        "lightness": lightness,
                        "temperature": self._attr_color_temp,
                    }
                )
            else:
                self.coordinator.data = {
                    "onoff": 1,
                    "lightness": lightness,
                    "temperature": self._attr_color_temp,
                }

            self._attr_color_mode = ColorMode.COLOR_TEMP
            self.async_write_ha_state()
            self.coordinator.hass.async_create_task(self.force_manual_update())
            return

        _LOGGER.info(f"Monochrome {self} turned on")
        # --- Monochrome ---
        # Use device-specific topic: {gateway_topic}/lights/{device_name}/power
        power_topic = TOPIC_SET_DEVICE_POWER.format(
            prefix=self.topic_prefix, device_name=self._device_name
        )

        # API expects boolean true/false directly, not a JSON object
        power_command = True

        # Add brightness if specified, otherwise use last known lightness
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            # Convert to 0-1 scale (API uses 0-1 for lightness)
            lightness_value = brightness / 255.0
            # Round to 2 decimal places, rounding up
            # Multiply by 100, round up with ceil, then divide by 100
            lightness_value = math.ceil(lightness_value * 100) / 100.0

            # Store as last known lightness
            self._last_known_lightness = lightness_value

            # Set power first
            # Todo: check if setting the brightness is enough - auto turn on if lightness > 0 ??
            await self.mqtt_client.async_publish(power_topic, power_command, qos=1)

            # Then set brightness using device-specific lightness topic
            lightness_topic = TOPIC_SET_DEVICE_LIGHTNESS.format(
                prefix=self.topic_prefix, device_name=self._device_name
            )
            lightness_command = {"lightness": lightness_value}
            await self.mqtt_client.async_publish(lightness_topic, lightness_command, qos=1)

            # Optimistically update state with both power and lightness values we just set
            if self.coordinator.data:
                self.coordinator.data.update({"onoff": 1, "lightness": lightness_value})
            else:
                self.coordinator.data = {"onoff": 1, "lightness": lightness_value}
        else:
            # No brightness specified - use last known lightness if available
            if self._last_known_lightness is not None:
                lightness_value = self._last_known_lightness
                # Round to 2 decimal places, rounding up
                lightness_value = math.ceil(lightness_value * 100) / 100.0
                
                # Set power first
                await self.mqtt_client.async_publish(power_topic, power_command, qos=1)
                
                # Then set brightness using device-specific lightness topic
                lightness_topic = TOPIC_SET_DEVICE_LIGHTNESS.format(
                    prefix=self.topic_prefix, device_name=self._device_name
                )
                lightness_command = {"lightness": lightness_value}
                await self.mqtt_client.async_publish(lightness_topic, lightness_command, qos=1)
                
                # Optimistically update state with both power and lightness values we just set
                if self.coordinator.data:
                    self.coordinator.data.update({"onoff": 1, "lightness": lightness_value})
                else:
                    self.coordinator.data = {"onoff": 1, "lightness": lightness_value}
            else:
                # No last known lightness - just turn on without setting brightness
                await self.mqtt_client.async_publish(power_topic, power_command, qos=1)
                
                # Optimistically update state with power value we just set
                if self.coordinator.data:
                    self.coordinator.data.update({"onoff": 1})
                else:
                    self.coordinator.data = {"onoff": 1}

        self.async_write_ha_state()
        self.coordinator.hass.async_create_task(self.force_manual_update())

    async def force_manual_update(self) -> None:
        """
        After a change - try requesting actual value either per forced mqtt update or via PollPriority
        :return:
        """
        await asyncio.sleep(1.0)
        # next polling cycle is >3s (this 1s + 2s Relationpolling min cycle)
        self.set_high_priority()
        if self.coordinator.polling_mode == POLLING_MODE_NORMAL:
            # Schedule a lightnessGet request 5 seconds after setting to get final value after ramping
            # Power state is inferred from lightness, so no need to poll power separately
            await asyncio.sleep(4.0)  # Wait 5 seconds for ramping to complete
            if self._is_multiwhite:
                _type = "Multiwhite"
                get_lightness_topic = TOPIC_GET_DEVICE_CTL.format(
                    prefix=self.topic_prefix, device_name=self._device_name
                )
            else:
                _type = "Monochrome"
                get_lightness_topic = TOPIC_GET_DEVICE_LIGHTNESS.format(
                    prefix=self.topic_prefix, device_name=self._device_name
                )
            _LOGGER.info(f"requesting manual update for {_type} {self._device_name} with Normal Polling")
            await self.mqtt_client.async_publish(get_lightness_topic, {}, qos=1)
        else:
            _LOGGER.info(f"requesting manual update for {self._device_name} via RationalPolling")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        # Use device-specific topic: {gateway_topic}/lights/{device_name}/power
        power_topic = TOPIC_SET_DEVICE_POWER.format(
            prefix=self.topic_prefix, device_name=self._device_name
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
        self.coordinator.hass.async_create_task(self.force_manual_update())
