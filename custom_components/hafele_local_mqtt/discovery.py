"""Device discovery for Hafele Local MQTT."""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    EVENT_DEVICES_UPDATED,
    TOPIC_DISCOVERY_GROUPS,
    TOPIC_DISCOVERY_LIGHTS,
    TOPIC_DISCOVERY_SCENES,
)
from .mqtt_client import HafeleMQTTClient

_LOGGER = logging.getLogger(__name__)


class HafeleDiscovery:
    """Handle device discovery from MQTT topics."""

    def __init__(
        self, hass: HomeAssistant, mqtt_client: HafeleMQTTClient, topic_prefix: str
    ) -> None:
        """Initialize discovery."""
        self.hass = hass
        self.mqtt_client = mqtt_client
        self.topic_prefix = topic_prefix
        self.devices: dict[int, dict[str, Any]] = {}
        self.groups: dict[int, dict[str, Any]] = {}
        self.scenes: dict[int, dict[str, Any]] = {}
        self._unsubscribers: list[Callable[[], None]] = []

    async def async_start(self) -> None:
        """Start discovery by subscribing to MQTT topics."""
        _LOGGER.info("Starting Hafele device discovery")

        # Subscribe to discovery topics
        lights_topic = TOPIC_DISCOVERY_LIGHTS.format(prefix=self.topic_prefix)
        groups_topic = TOPIC_DISCOVERY_GROUPS.format(prefix=self.topic_prefix)
        scenes_topic = TOPIC_DISCOVERY_SCENES.format(prefix=self.topic_prefix)

        unsub_lights = await self.mqtt_client.async_subscribe(
            lights_topic, self._on_lights_message
        )
        unsub_groups = await self.mqtt_client.async_subscribe(
            groups_topic, self._on_groups_message
        )
        unsub_scenes = await self.mqtt_client.async_subscribe(
            scenes_topic, self._on_scenes_message
        )

        self._unsubscribers.extend([unsub_lights, unsub_groups, unsub_scenes])

    async def async_stop(self) -> None:
        """Stop discovery."""
        for unsub in self._unsubscribers:
            if callable(unsub):
                unsub()
        self._unsubscribers.clear()
        _LOGGER.info("Stopped Hafele device discovery")

    def _on_lights_message(self, topic: str, payload: Any) -> None:
        """Handle lights discovery message."""
        try:
            if isinstance(payload, str):
                lights = json.loads(payload)
            else:
                lights = payload

            if not isinstance(lights, list):
                _LOGGER.warning("Invalid lights payload format: %s", type(lights))
                return

            _LOGGER.info("Discovered %d lights", len(lights))

            for light in lights:
                device_addr = light.get("device_addr")
                if device_addr is not None:
                    self.devices[device_addr] = light
                    _LOGGER.debug(
                        "Discovered light: %s (addr: %s)",
                        light.get("device_name"),
                        device_addr,
                    )

            # Notify that devices have been updated
            # Platforms will check discovery on their next update
            self.hass.bus.async_fire(EVENT_DEVICES_UPDATED)

        except (json.JSONDecodeError, KeyError, TypeError) as err:
            _LOGGER.error("Error parsing lights message: %s", err)

    def _on_groups_message(self, topic: str, payload: Any) -> None:
        """Handle groups discovery message."""
        try:
            if isinstance(payload, str):
                groups = json.loads(payload)
            else:
                groups = payload

            if not isinstance(groups, list):
                _LOGGER.warning("Invalid groups payload format: %s", type(groups))
                return

            _LOGGER.info("Discovered %d groups", len(groups))

            for group in groups:
                group_addr = group.get("group_main_addr")
                if group_addr is not None:
                    self.groups[group_addr] = group
                    _LOGGER.debug(
                        "Discovered group: %s (addr: %s)",
                        group.get("group_name"),
                        group_addr,
                    )

        except (json.JSONDecodeError, KeyError, TypeError) as err:
            _LOGGER.error("Error parsing groups message: %s", err)

    def _on_scenes_message(self, topic: str, payload: Any) -> None:
        """Handle scenes discovery message."""
        try:
            if isinstance(payload, str):
                scenes = json.loads(payload)
            else:
                scenes = payload

            if not isinstance(scenes, list):
                _LOGGER.warning("Invalid scenes payload format: %s", type(scenes))
                return

            _LOGGER.info("Discovered %d scenes", len(scenes))

            for scene in scenes:
                scene_id = scene.get("scene_id")
                if scene_id is not None:
                    self.scenes[scene_id] = scene
                    _LOGGER.debug(
                        "Discovered scene: %s (id: %s)",
                        scene.get("scene_name"),
                        scene_id,
                    )

        except (json.JSONDecodeError, KeyError, TypeError) as err:
            _LOGGER.error("Error parsing scenes message: %s", err)

    def get_device(self, device_addr: int) -> dict[str, Any] | None:
        """Get device information by address."""
        return self.devices.get(device_addr)

    def get_all_devices(self) -> dict[int, dict[str, Any]]:
        """Get all discovered devices."""
        return self.devices.copy()

    def get_group(self, group_addr: int) -> dict[str, Any] | None:
        """Get group information by address."""
        return self.groups.get(group_addr)

    def get_all_groups(self) -> dict[int, dict[str, Any]]:
        """Get all discovered groups."""
        return self.groups.copy()

    def get_scene(self, scene_id: int) -> dict[str, Any] | None:
        """Get scene information by ID."""
        return self.scenes.get(scene_id)

    def get_all_scenes(self) -> dict[int, dict[str, Any]]:
        """Get all discovered scenes."""
        return self.scenes.copy()

