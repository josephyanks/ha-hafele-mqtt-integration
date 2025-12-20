"""Light platform for Hafele Local MQTT."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any, Callable

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
    TOPIC_SET_DEVICE_LIGHTNESS,
    TOPIC_SET_DEVICE_POWER,
    TOPIC_DEVICE_STATUS,
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
    ) -> None:
        """Initialize the coordinator."""
        self.mqtt_client = mqtt_client
        self.device_addr = device_addr
        self.device_name = device_name
        self.topic_prefix = topic_prefix
        self.polling_timeout = polling_timeout
        self._status_data: dict[str, Any] = {}
        self._status_received = False
        self._unsubscribers: list = []

        # URL encode device name for MQTT topic (handles spaces and special chars)
        from urllib.parse import quote
        encoded_device_name = quote(device_name, safe="")

        # Subscribe to device-specific status topic
        status_topic = TOPIC_DEVICE_STATUS.format(
            prefix=topic_prefix, device_name=encoded_device_name
        )

        _LOGGER.debug(
            "Setting up status subscription for device %s (name: %s, encoded: %s) on topic: %s",
            device_addr,
            device_name,
            encoded_device_name,
            status_topic,
        )

        # Device-specific status topic
        self.response_topics = [status_topic]
        self._encoded_device_name = encoded_device_name

        super().__init__(
            hass,
            _LOGGER,
            name=f"hafele_light_{device_addr}",
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
        import asyncio

        # Request status using getDevicePower and getDeviceLightness operations
        get_power_topic = TOPIC_GET_DEVICE_POWER.format(
            prefix=self.topic_prefix, device_name=self._encoded_device_name
        )
        get_lightness_topic = TOPIC_GET_DEVICE_LIGHTNESS.format(
            prefix=self.topic_prefix, device_name=self._encoded_device_name
        )

        _LOGGER.debug(
            "Requesting status for device %s (name: %s) on topics: %s, %s",
            self.device_addr,
            self.device_name,
            get_power_topic,
            get_lightness_topic,
        )

        # Reset status received flag
        self._status_received = False
        # Keep a copy of existing data to preserve it if no response comes
        old_data = self._status_data.copy() if isinstance(self._status_data, dict) else {}

        # Request both power and lightness status
        await self.mqtt_client.async_publish(get_power_topic, {}, qos=1)
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

    # Track which entities we've already created
    created_entities: set[int] = set()

    async def _create_entities_for_devices() -> None:
        """Create entities for all discovered light devices."""
        devices = discovery.get_all_devices()
        new_entities = []

        for device_addr, device_info in devices.items():
            # Skip if we've already created this entity
            if device_addr in created_entities:
                continue

            # Only create entities for lights
            # Since these come from the lights discovery topic, they should all be lights
            # But check device_types if it exists to be safe
            device_types = device_info.get("device_types", [])
            if device_types and "Light" not in device_types:
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
            )

            # Set up subscriptions to device status topic
            await coordinator._async_setup_subscriptions()
            
            # Start individual coordinator polling
            # Use async_request_refresh instead of async_config_entry_first_refresh
            # since we don't have a config entry reference in the coordinator
            await coordinator.async_request_refresh()

            # Create entity
            entity = HafeleLightEntity(
                coordinator, device_addr, device_info, mqtt_client, topic_prefix
            )
            new_entities.append(entity)
            created_entities.add(device_addr)

        if new_entities:
            _LOGGER.info("Adding %d new light entities", len(new_entities))
            async_add_entities(new_entities)

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
        self._attr_unique_id = f"hafele_light_{device_addr}"
        self._attr_name = device_info.get("device_name", f"Hafele Light {device_addr}")
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._attr_color_mode = ColorMode.BRIGHTNESS

        # Store device name and URL encode it for MQTT topics
        from urllib.parse import quote
        device_name = device_info.get("device_name", f"device_{device_addr}")
        self._device_name = device_name
        self._encoded_device_name = quote(device_name, safe="")

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
    def is_on(self) -> bool:
        """Return if the light is on."""
        if not self.coordinator.data:
            return False

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

        return False

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
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
            # Fallback to other common formats for compatibility
            brightness = status.get("brightness")
            if brightness is not None:
                if isinstance(brightness, (int, float)):
                    if brightness > 255:
                        # Assume 0-100 scale
                        return int((brightness / 100) * 255)
                    return int(brightness)
            level = status.get("level")
            if level is not None:
                if isinstance(level, (int, float)):
                    if level > 255:
                        return int((level / 100) * 255)
                    return int(level)

        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        # Use device-specific topic: {gateway_topic}/lights/{device_name}/setDevicePower
        power_topic = TOPIC_SET_DEVICE_POWER.format(
            prefix=self.topic_prefix, device_name=self._encoded_device_name
        )

        # Build command payload - API uses "onOff" not "power"
        command: dict[str, Any] = {"onOff": "on"}

        # Add brightness if specified
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            # Convert to 0-1 scale (API uses 0-1 for lightness)
            lightness_value = brightness / 255.0
            
            # Set power first
            await self.mqtt_client.async_publish(power_topic, command, qos=1)
            
            # Then set brightness using device-specific lightness topic
            lightness_topic = TOPIC_SET_DEVICE_LIGHTNESS.format(
                prefix=self.topic_prefix, device_name=self._encoded_device_name
            )
            lightness_command = {"lightness": lightness_value}
            await self.mqtt_client.async_publish(lightness_topic, lightness_command, qos=1)
        else:
            await self.mqtt_client.async_publish(power_topic, command, qos=1)

        # Optimistically update state
        if self.coordinator.data:
            self.coordinator.data.update(command)
        else:
            self.coordinator.data = command

        self.async_write_ha_state()

        # Request updated status after a short delay
        # This ensures the set command has been processed before requesting status
        async def _refresh_status() -> None:
            await asyncio.sleep(0.2)  # 200ms delay
            # Always request both power and lightness status after turning on
            get_power_topic = TOPIC_GET_DEVICE_POWER.format(
                prefix=self.topic_prefix, device_name=self._encoded_device_name
            )
            get_lightness_topic = TOPIC_GET_DEVICE_LIGHTNESS.format(
                prefix=self.topic_prefix, device_name=self._encoded_device_name
            )
            await self.mqtt_client.async_publish(get_power_topic, {}, qos=1)
            await self.mqtt_client.async_publish(get_lightness_topic, {}, qos=1)
        
        hass = self.coordinator.hass
        hass.async_create_task(_refresh_status())

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        # Use device-specific topic: {gateway_topic}/lights/{device_name}/setDevicePower
        power_topic = TOPIC_SET_DEVICE_POWER.format(
            prefix=self.topic_prefix, device_name=self._encoded_device_name
        )

        # API uses "onOff" not "power"
        command = {"onOff": "off"}

        await self.mqtt_client.async_publish(power_topic, command, qos=1)

        # Optimistically update state
        if self.coordinator.data:
            self.coordinator.data.update(command)
        else:
            self.coordinator.data = command

        self.async_write_ha_state()

        # Request updated status after a short delay
        # This ensures the set command has been processed before requesting status
        async def _refresh_status() -> None:
            await asyncio.sleep(0.2)  # 200ms delay
            get_power_topic = TOPIC_GET_DEVICE_POWER.format(
                prefix=self.topic_prefix, device_name=self._encoded_device_name
            )
            await self.mqtt_client.async_publish(get_power_topic, {}, qos=1)
        
        hass = self.coordinator.hass
        hass.async_create_task(_refresh_status())

