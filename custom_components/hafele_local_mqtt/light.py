"""Light platform for Hafele Local MQTT."""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

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
    TOPIC_LIGHT_STATUS,
    TOPIC_SET_DEVICE_LIGHTNESS,
    TOPIC_SET_DEVICE_POWER,
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

        # Subscribe to the lightStatus topic (operation-based, not device-based)
        # We'll filter messages by device_name in the payload
        status_topic = TOPIC_LIGHT_STATUS.format(prefix=topic_prefix)

        _LOGGER.debug(
            "Setting up status subscription for device %s (name: %s) on topic: %s",
            device_addr,
            device_name,
            status_topic,
        )

        # Single status topic - we filter by device_name in the message handler
        self.response_topics = [status_topic]

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

            # Filter by device_name - only process messages for this device
            message_device_name = data.get("device_name")
            if message_device_name != self.device_name:
                # Not for this device, ignore
                return

            self._status_data = data
            self._status_received = True
            _LOGGER.debug(
                "Received status for device %s (name: %s): %s",
                self.device_addr,
                self.device_name,
                data,
            )
            # Notify coordinator that data is available
            self.async_set_updated_data(data)

        except (json.JSONDecodeError, TypeError, AttributeError) as err:
            _LOGGER.error(
                "Error parsing status message for device %s: %s",
                self.device_addr,
                err,
            )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch status from device via MQTT polling."""
        import asyncio

        # Request status using operation-based topic
        # Try both getDevicePower and getDeviceLightness to get full status
        get_power_topic = TOPIC_GET_DEVICE_POWER.format(prefix=self.topic_prefix)
        get_lightness_topic = TOPIC_GET_DEVICE_LIGHTNESS.format(prefix=self.topic_prefix)
        
        # Payload contains device_name per API docs
        payload = {"device_name": self.device_name}

        _LOGGER.debug(
            "Requesting status for device %s (name: %s) on topics: %s, %s with payload: %s",
            self.device_addr,
            self.device_name,
            get_power_topic,
            get_lightness_topic,
            payload,
        )

        # Reset status received flag
        self._status_received = False
        old_data = self._status_data.copy()
        
        # Request both power and lightness status
        await self.mqtt_client.async_publish(get_power_topic, payload, qos=1)
        await self.mqtt_client.async_publish(get_lightness_topic, payload, qos=1)

        # Wait for response (with timeout)
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
            # Return old data if available, otherwise empty dict
            return old_data if old_data else {}

        return self._status_data


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

            # Create coordinator for polling
            coordinator = HafeleLightCoordinator(
                hass,
                mqtt_client,
                device_addr,
                device_name,
                topic_prefix,
                polling_interval,
                polling_timeout,
            )

            # Set up subscriptions
            await coordinator._async_setup_subscriptions()

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

        # Device name is used in payloads, not topics (no encoding needed)
        self._device_name = device_info.get("device_name", f"device_{device_addr}")

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

        # Parse status data - adjust based on actual API response format
        status = self.coordinator.data
        # Try common field names
        if isinstance(status, dict):
            # Check for on/off state in various possible formats
            power = status.get("power")
            if power is not None:
                return power in ("on", "ON", True, 1, "1")
            state = status.get("state")
            if state is not None:
                return state in ("on", "ON", True, 1, "1")
            is_on = status.get("is_on")
            if is_on is not None:
                return bool(is_on)

        return False

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        if not self.coordinator.data:
            return None

        status = self.coordinator.data
        if isinstance(status, dict):
            # Try common brightness field names
            brightness = status.get("brightness")
            if brightness is not None:
                # Convert to 0-255 range if needed
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
        # Use operation-based topic with device_name in payload
        set_topic = TOPIC_SET_DEVICE_POWER.format(prefix=self.topic_prefix)

        # Build command payload with device_name per API docs
        command: dict[str, Any] = {
            "device_name": self.device_info.get("device_name"),
            "power": "on",
        }

        # Add brightness if specified - use setDeviceLightness for brightness
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            # Convert to 0-1 scale (API uses 0-1 for lightness)
            lightness_value = brightness / 255.0
            
            # Set power first, then lightness
            await self.mqtt_client.async_publish(set_topic, command, qos=1)
            
            # Set brightness using setDeviceLightness
            lightness_topic = TOPIC_SET_DEVICE_LIGHTNESS.format(prefix=self.topic_prefix)
            lightness_command = {
                "device_name": self.device_info.get("device_name"),
                "lightness": lightness_value,
            }
            await self.mqtt_client.async_publish(lightness_topic, lightness_command, qos=1)
        else:
            await self.mqtt_client.async_publish(set_topic, command, qos=1)

        # Optimistically update state
        if self.coordinator.data:
            self.coordinator.data.update(command)
        else:
            self.coordinator.data = command

        self.async_write_ha_state()

        # Request updated status
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        # Use operation-based topic with device_name in payload
        set_topic = TOPIC_SET_DEVICE_POWER.format(prefix=self.topic_prefix)

        command = {
            "device_name": self.device_info.get("device_name"),
            "power": "off",
        }

        await self.mqtt_client.async_publish(set_topic, command, qos=1)

        # Optimistically update state
        if self.coordinator.data:
            self.coordinator.data.update(command)
        else:
            self.coordinator.data = command

        self.async_write_ha_state()

        # Request updated status
        await self.coordinator.async_request_refresh()

