"""Light platform for Hafele Local MQTT."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import math
from datetime import timedelta
from typing import Any
import re

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
    ATTR_COLOR_TEMP_KELVIN,
)

from homeassistant.components.group.light import LightGroup

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
    CONF_ENABLE_GROUPS,
    DOMAIN,
    EVENT_DEVICES_UPDATED,
    TOPIC_GET_DEVICE_LIGHTNESS,
    TOPIC_SET_DEVICE_CTL,
    TOPIC_GET_DEVICE_CTL,
    TOPIC_SET_DEVICE_LIGHTNESS,
    TOPIC_SET_DEVICE_POWER,
    TOPIC_DEVICE_STATUS,
    DEFAULT_POLLING_MODE,
    POLLING_MODE_NORMAL,
    POLLING_MODE_ROTATIONAL,
    TOPIC_SET_GROUP_POWER,
    TOPIC_SET_GROUP_LIGHTNESS,
    TOPIC_SET_GROUP_CTL,
)
from .discovery import HafeleDiscovery
from .mqtt_client import HafeleMQTTClient

_LOGGER = logging.getLogger(__name__)


def _suggested_object_id_from_name(name: str) -> str:
    """Build a Home Assistant object id fragment from a mesh device or group name."""
    entity_id_base = name.lower().replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]", "", entity_id_base).strip("_")


def _light_entity_id_for_device(
    entity_registry: er.EntityRegistry,
    device_addr: int,
    dev_info: dict[str, Any],
) -> str | None:
    """Resolve a light entity_id from the registry, falling back to sanitized device name."""
    unique_id = f"hafele_{device_addr}"
    entity_id = entity_registry.async_get_entity_id("light", DOMAIN, unique_id)
    if entity_id:
        return entity_id
    name = dev_info.get("device_name", f"device_{device_addr}").strip()
    clean_id = _suggested_object_id_from_name(name)
    return f"light.{clean_id}" if clean_id else None


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
        device_types: list,
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
        self.entity: HafeleLightEntity | None = None
        self.is_multiwhite = any(t.lower() == "multiwhite" for t in device_types)

        status_topic = TOPIC_DEVICE_STATUS.format(
            prefix=topic_prefix, device_name=device_name
        )

        self.response_topics = [status_topic]
        self._device_name = device_name

        update_interval = (
            timedelta(seconds=polling_interval)
            if polling_mode == POLLING_MODE_NORMAL
            else None
        )
        _type_str = "multiwhite" if self.is_multiwhite else "monochrome"
        _LOGGER.debug(
            "Setting up status subscription for device %s (name: %s) type (%s) on topic: %s with update interval %s",
            device_addr,
            device_name,
            _type_str,
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
                if data["lightness"] > 0:
                    data["onoff"] = 1
                else:
                    data["onoff"] = 0
                _LOGGER.debug(f'Updating onoff to {data["onoff"]} due to lightness {data["lightness"]}')

            if isinstance(data, dict) and isinstance(self._status_data, dict):
                self._status_data.update(data)
                merged_data = self._status_data
            else:
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
            self.async_set_updated_data(merged_data)

            if self.entity and self.entity.hass:
                self.entity.hass.async_create_task(self.entity.async_update_parent_groups())

        except (json.JSONDecodeError, TypeError) as err:
            _LOGGER.error(
                "Error parsing status message for device %s: %s",
                self.device_addr,
                err,
            )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch status from device via MQTT polling."""
        if self.is_multiwhite:
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

        self._status_received = False
        old_data = self._status_data.copy() if isinstance(self._status_data, dict) else {}

        await self.mqtt_client.async_publish(get_lightness_topic, {}, qos=1)

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
            return old_data if old_data else {}

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
    enable_groups = entry.data.get(CONF_ENABLE_GROUPS, True)
    _LOGGER.debug(f"async_setup_entry: topic_prefix {topic_prefix}, polling mode: {polling_mode},"
                  f" polling interval {polling_interval}")

    created_entities: set[int] = set()
    created_groups: set[int] = set()
    coordinators: dict[int, HafeleLightCoordinator] = {}
    entity_registry = er.async_get(hass)

    async def _create_entities_for_devices_and_groups() -> None:
        """Create entities for all discovered light devices and groups."""
        new_entities = []

        devices = discovery.get_all_devices()
        for device_addr, device_info in devices.items():
            if device_addr in created_entities:
                continue
            
            unique_id = f"hafele_{device_addr}"
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

            device_types = device_info.get("device_types", [])

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

            device_name = device_info.get("device_name", f"device_{device_addr}")

            coordinator = HafeleLightCoordinator(
                hass,
                mqtt_client,
                device_addr,
                device_name,
                topic_prefix,
                polling_interval,
                polling_timeout,
                polling_mode,
                device_types,
            )

            await coordinator._async_setup_subscriptions()

            entity = HafeleLightEntity(
                coordinator, device_addr, device_info, mqtt_client, topic_prefix
            )

            coordinator.entity = entity
            coordinators[device_addr] = coordinator

            new_entities.append(entity)
            created_entities.add(device_addr)

            suggested_object_id = _suggested_object_id_from_name(device_name)
            entity_registry.async_get_or_create(
                "light", DOMAIN, entity.unique_id, suggested_object_id=suggested_object_id
            )

        if enable_groups:
            discovered_groups = discovery.get_all_groups()
            for group_addr, group_info in discovered_groups.items():
                if group_addr in created_groups:
                    continue

                group_name = group_info.get("group_name")
                if not group_name:
                    continue

                member_device_addresses = group_info.get("devices", [])
                child_entity_ids: list[str] = []
                for addr in member_device_addresses:
                    dev_info = discovery.get_device(addr)
                    if dev_info:
                        entity_id = _light_entity_id_for_device(
                            entity_registry, addr, dev_info
                        )
                        if entity_id:
                            child_entity_ids.append(entity_id)

                _LOGGER.info(
                    "Creating native group: %s (addr: %s) mapping to entities: %s",
                    group_name,
                    group_addr,
                    child_entity_ids,
                )

                group_entity = HafeleMeshLightGroup(
                    group_addr, group_name, child_entity_ids, mqtt_client, topic_prefix
                )
                new_entities.append(group_entity)
                created_groups.add(group_addr)

                suggested_group_obj_id = _suggested_object_id_from_name(group_name)
                entity_registry.async_get_or_create(
                    "light",
                    DOMAIN,
                    group_entity.unique_id,
                    suggested_object_id=suggested_group_obj_id,
                )

        if new_entities:
            _LOGGER.info("Adding %d light entities", len(new_entities))
            async_add_entities(new_entities, update_before_add=False)
            _LOGGER.info("Finished adding %d light entities", len(new_entities))

    @callback
    def _on_devices_updated(event) -> None:
        """Handle device discovery update event."""
        hass.async_create_task(_create_entities_for_devices_and_groups())

    entry.async_on_unload(
        hass.bus.async_listen(EVENT_DEVICES_UPDATED, _on_devices_updated)
    )

    await _create_entities_for_devices_and_groups()

    if polling_mode == POLLING_MODE_ROTATIONAL:
        async def _rotational_polling_loop() -> None:
            """Rotational Polling with Fine-Grained PollPriority and sleep after each update."""
            rr_index = 0
            _LOGGER.debug("Starting rational polling loop")
            await hass.async_block_till_done()
            _LOGGER.info("Homeassistant started - we start polling")
            while True:
                try:
                    entity = None
                    is_high = False
                    normal_entities = []

                    for c in coordinators.values():
                        e = c.entity
                        if e is None:
                            continue
                        if e.priority == PollPriority.HIGH:
                            entity = e
                            is_high = True
                            break
                        normal_entities.append(e)

                    if entity is None and normal_entities:
                        entity = normal_entities[rr_index % len(normal_entities)]

                    if entity is None:
                        _LOGGER.warning("No entities found to poll")
                        await asyncio.sleep(polling_interval)
                        continue

                    try:
                        if is_high:
                            _LOGGER.debug(
                                "Updating HIGH priority entity: %s (%s)",
                                entity.device_name,
                                entity.device_addr,
                            )
                            await entity.coordinator.async_request_refresh()
                            entity.reset_priority()
                        else:
                            _LOGGER.debug(
                                "Updating NORMAL priority entity: %s (%s)",
                                entity.device_name,
                                entity.device_addr,
                            )
                            await entity.coordinator.async_request_refresh()
                            rr_index += 1
                    except Exception as e:
                        _LOGGER.exception(
                            "Error updating %s entity %s: %s",
                            "HIGH" if is_high else "normal",
                            entity.device_name,
                            e,
                        )
                    await asyncio.sleep(polling_interval)

                except Exception as cycle_error:
                    _LOGGER.exception(f"Critical error in polling cycle: {cycle_error}")
                    await asyncio.sleep(polling_interval)

        @callback
        def _start_rotational_polling(event):
            hass.async_create_task(_rotational_polling_loop())
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start_rotational_polling)
        _LOGGER.info("Rotational polling mode enabled - polling one device at a time")
    else:
        _LOGGER.info("Normal polling mode enabled - each device polls independently")


class PollPriority:
    """Polling update priority; lower values are refreshed sooner."""
    NORMAL = 5
    HIGH = 1


async def run_one_rotational_polling_cycle(
    coordinators: dict[int, "HafeleLightCoordinator"],
    rr_index: int,
    polling_interval: int,
) -> int:
    """Run one cycle of rotational polling."""
    high_priority_entities: list[HafeleLightEntity] = []
    normal_entities: list[HafeleLightEntity] = []
    for c in coordinators.values():
        entity = c.entity
        if entity is None:
            continue
        if entity.priority == PollPriority.HIGH:
            high_priority_entities.append(entity)
        else:
            normal_entities.append(entity)
    if not high_priority_entities and not normal_entities:
        await asyncio.sleep(polling_interval)
        return rr_index
    for entity in high_priority_entities:
        try:
            await entity.coordinator.async_request_refresh()
            entity.reset_priority()
        except Exception as e:
            _LOGGER.exception(
                "Error updating HIGH priority entity %s: %s",
                entity.device_name, e,
            )
        await asyncio.sleep(polling_interval)
    if normal_entities:
        entity = normal_entities[rr_index % len(normal_entities)]
        try:
            await entity.coordinator.async_request_refresh()
            rr_index += 1
        except Exception as e:
            _LOGGER.exception(
                "Error updating normal entity %s: %s",
                entity.device_name, e,
            )
        await asyncio.sleep(polling_interval)
    return rr_index


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
        self._attr_unique_id = f"hafele_{device_addr}"
        self._attr_name = device_info.get("device_name", f"Hafele Light {device_addr}")

        device_types = device_info.get("device_types", [])
        self._is_multiwhite = any(t.lower() == "multiwhite" for t in device_types)
        self._attr_color_mode = (
            ColorMode.COLOR_TEMP if self._is_multiwhite else ColorMode.BRIGHTNESS
        )
        if self._is_multiwhite:
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
        else:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

        device_name = device_info.get("device_name", f"device_{device_addr}")
        self._device_name = device_name
        
        self._last_known_lightness: float | None = None
        self._last_known_color_temp: int = 2700

        self._priority = PollPriority.NORMAL

        location = device_info.get("location", "Unknown")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_addr))},
            name=self._attr_name,
            manufacturer="Hafele",
            model="Local MQTT Light",
            suggested_area=location,
        )
        _LOGGER.info(f"initiated {self} - multiwhite: {self._is_multiwhite}")

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def is_multiwhite(self) -> bool:
        return self._is_multiwhite

    @property
    def priority(self) -> int:
        return self._priority

    def set_high_priority(self):
        self._priority = PollPriority.HIGH

    def reset_priority(self):
        self._priority = PollPriority.NORMAL

    @property
    def min_color_temp_kelvin(self) -> int:
        return 2700

    @property
    def max_color_temp_kelvin(self) -> int:
        return 5000

    @property
    def is_on(self) -> bool:
        """Return if the light is on."""
        if not self.coordinator.data:
            return False

        status = self.coordinator.data
        if isinstance(status, dict):
            onoff = status.get("onoff")
            if onoff is not None:
                return bool(onoff) if isinstance(onoff, (int, float)) else onoff in ("on", "ON", True, 1, "1")
            
            on_off = status.get("onOff")
            if on_off is not None:
                if isinstance(on_off, (int, float)):
                    return bool(on_off)
                return on_off in ("on", "ON", True, 1, "1")
            
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
    def color_temp_kelvin(self) -> int | None:
        """Return the color_temperature of the light."""
        if not self._is_multiwhite:
            return None
        if not self.coordinator.data:
            return None
        status = self.coordinator.data
        if isinstance(status, dict):
            temp_kelvin = status.get("temperature")
            if temp_kelvin is not None:
                return min(max(temp_kelvin, 2700), 5000)
        return 2700

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        if not self.coordinator.data:
            return 0

        status = self.coordinator.data
        if isinstance(status, dict):
            lightness = status.get("lightness")
            if lightness is not None:
                if isinstance(lightness, (int, float)):
                    lightness_float = float(lightness)
                    self._last_known_lightness = lightness_float
                    return int(lightness_float * 255)
            brightness = status.get("brightness")
            if brightness is not None:
                if isinstance(brightness, (int, float)):
                    if brightness > 255:
                        brightness_value = int((brightness / 100) * 255)
                    else:
                        brightness_value = int(brightness)
                    self._last_known_lightness = brightness_value / 255.0
                    return brightness_value
            level = status.get("level")
            if level is not None:
                if isinstance(level, (int, float)):
                    if level > 255:
                        level_value = int((level / 100) * 255)
                    else:
                        level_value = int(level)
                    self._last_known_lightness = level_value / 255.0
                    return level_value

        if self._last_known_lightness is not None:
            return int(self._last_known_lightness * 255)
        return 0

    async def async_update_parent_groups(self) -> None:
        """Find and tell any parent group containing this light to instantly recalculate state."""
        for entity in self.hass.data["light"].entities:
            if isinstance(entity, HafeleMeshLightGroup) and self.entity_id in entity.tracking_child_ids:
                entity.async_update_group_state_from_children()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        # --- MULTIWHITE ---
        if self._is_multiwhite:
            _LOGGER.info(f"Multiwhite {self} turned on")
            if ATTR_BRIGHTNESS in kwargs:
                brightness = kwargs[ATTR_BRIGHTNESS]
                lightness = math.ceil((brightness / 255.0) * 100) / 100.0
                self._last_known_lightness = lightness
            else:
                lightness = self._last_known_lightness or 1.0

            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                self._last_known_color_temp = min(max(temp_kelvin, 2700), 5000)

            payload_ctl = {
                "lightness": lightness,
                "temperature": self._last_known_color_temp,
            }
            topic_ctl = TOPIC_SET_DEVICE_CTL.format(
                prefix=self.topic_prefix, device_name=self._device_name
            )

            await self.mqtt_client.async_publish(topic_ctl, payload_ctl, qos=1)
            state_update = {
                "onoff": 1,
                "lightness": lightness,
                "temperature": self._last_known_color_temp,
            }
            if self.coordinator.data:
                self.coordinator.data.update(state_update)
            else:
                self.coordinator.data = state_update

            self._attr_color_mode = ColorMode.COLOR_TEMP
        else:
            _LOGGER.info(f"Monochrome {self} turned on")
            # --- Monochrome ---
            power_topic = TOPIC_SET_DEVICE_POWER.format(
                prefix=self.topic_prefix, device_name=self._device_name
            )

            power_command = True

            if ATTR_BRIGHTNESS in kwargs:
                brightness = kwargs[ATTR_BRIGHTNESS]
                lightness_value = brightness / 255.0
                lightness_value = math.ceil(lightness_value * 100) / 100.0
                self._last_known_lightness = lightness_value

                await self.mqtt_client.async_publish(power_topic, power_command, qos=1)

                lightness_topic = TOPIC_SET_DEVICE_LIGHTNESS.format(
                    prefix=self.topic_prefix, device_name=self._device_name
                )
                lightness_command = {"lightness": lightness_value}
                await self.mqtt_client.async_publish(lightness_topic, lightness_command, qos=1)

                state_update = {"onoff": 1, "lightness": lightness_value}
                if self.coordinator.data:
                    self.coordinator.data.update(state_update)
                else:
                    self.coordinator.data = state_update
            else:
                if self._last_known_lightness is not None:
                    lightness_value = self._last_known_lightness
                    lightness_value = math.ceil(lightness_value * 100) / 100.0
                    
                    await self.mqtt_client.async_publish(power_topic, power_command, qos=1)
                    
                    lightness_topic = TOPIC_SET_DEVICE_LIGHTNESS.format(
                        prefix=self.topic_prefix, device_name=self._device_name
                    )
                    lightness_command = {"lightness": lightness_value}
                    await self.mqtt_client.async_publish(lightness_topic, lightness_command, qos=1)
                    
                    state_update = {"onoff": 1, "lightness": lightness_value}
                    if self.coordinator.data:
                        self.coordinator.data.update(state_update)
                    else:
                        self.coordinator.data = state_update
                else:
                    await self.mqtt_client.async_publish(power_topic, power_command, qos=1)
                    
                    if self.coordinator.data:
                        self.coordinator.data.update({"onoff": 1})
                    else:
                        self.coordinator.data = {"onoff": 1}

        self.async_write_ha_state()
        await self.async_update_parent_groups()
        self.coordinator.hass.async_create_task(self.force_manual_update())

    async def force_manual_update(self) -> None:
        """After a change - try requesting actual value either per forced mqtt update or via PollPriority."""
        await asyncio.sleep(1.0)
        self.set_high_priority()
        if self.coordinator.polling_mode == POLLING_MODE_NORMAL:
            await asyncio.sleep(4.0)
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
        power_topic = TOPIC_SET_DEVICE_POWER.format(
            prefix=self.topic_prefix, device_name=self._device_name
        )

        power_command = False

        await self.mqtt_client.async_publish(power_topic, power_command, qos=1)

        if self.coordinator.data:
            self.coordinator.data.update({"onoff": 0, "lightness": 0.0})
        else:
            self.coordinator.data = {"onoff": 0, "lightness": 0.0}

        self.async_write_ha_state()
        await self.async_update_parent_groups()
        self.coordinator.hass.async_create_task(self.force_manual_update())


class HafeleMeshLightGroup(LightGroup):
    """Representation of a Häfele Mesh Group controlled via unified API payloads."""

    def __init__(
        self,
        group_addr: int,
        group_name: str,
        child_entity_ids: list[str],
        mqtt_client: HafeleMQTTClient,
        topic_prefix: str,
    ) -> None:
        """Initialize the single-call group entity."""
        self.group_addr = group_addr
        self.group_name = group_name
        self.mqtt_client = mqtt_client
        self.topic_prefix = topic_prefix
        self.tracking_child_ids = child_entity_ids

        self._power_topic = TOPIC_SET_GROUP_POWER.format(prefix=topic_prefix, group_name=group_name)
        self._lightness_topic = TOPIC_SET_GROUP_LIGHTNESS.format(prefix=topic_prefix, group_name=group_name)
        self._ctl_topic = TOPIC_SET_GROUP_CTL.format(prefix=topic_prefix, group_name=group_name)

        self._last_known_lightness: float = 1.0
        self._last_known_color_temp: int = 2700
        
        super().__init__(
            unique_id=f"hafele_group_{group_addr}",
            name=group_name,
            entity_ids=child_entity_ids,
            mode=False, 
        )

    @callback
    def async_update_group_state_from_children(self) -> None:
        """Force the group entity to immediately update its state from actual child data."""
        self.async_update_ha_state(True)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send a group action message to the mesh gateway and force direct child state changes."""
        _LOGGER.info("Group %s (%s) executing single-call update", self.name, self.group_addr)

        target_onoff = 1
        target_color_temp = self._last_known_color_temp

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            target_color_temp = min(max(kwargs[ATTR_COLOR_TEMP_KELVIN], 2700), 5000)
            self._last_known_color_temp = target_color_temp

        # Case 1: Brightness was explicitly adjusted via the group
        if ATTR_BRIGHTNESS in kwargs:
            target_lightness = math.ceil((kwargs[ATTR_BRIGHTNESS] / 255.0) * 100) / 100.0
            self._last_known_lightness = target_lightness

            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                payload = {"lightness": target_lightness, "temperature": target_color_temp}
                await self.mqtt_client.async_publish(self._ctl_topic, payload, qos=1)
            else:
                await self.mqtt_client.async_publish(self._power_topic, True, qos=1)
                await self.mqtt_client.async_publish(self._lightness_topic, {"lightness": target_lightness}, qos=1)

            # Cascade uniform values downward
            for entity_id in self.tracking_child_ids:
                child_entity = self.hass.data["light"].get_entity(entity_id)
                if child_entity and isinstance(child_entity, HafeleLightEntity):
                    child_entity._last_known_lightness = target_lightness
                    child_entity._last_known_color_temp = target_color_temp
                    mock_data = {"onoff": target_onoff, "lightness": target_lightness, "temperature": target_color_temp}
                    if child_entity.coordinator.data:
                        child_entity.coordinator.data.update(mock_data)
                    else:
                        child_entity.coordinator.data = mock_data
                    child_entity.async_write_ha_state()

        # Case 2: ONLY color temperature was changed. Preserve distinct child brightnesses.
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            for entity_id in self.tracking_child_ids:
                child_entity = self.hass.data["light"].get_entity(entity_id)
                if child_entity and isinstance(child_entity, HafeleLightEntity):
                    current_child_lightness = 1.0
                    if child_entity.coordinator.data and "lightness" in child_entity.coordinator.data:
                        current_child_lightness = child_entity.coordinator.data["lightness"]
                    elif child_entity._last_known_lightness is not None:
                        current_child_lightness = child_entity._last_known_lightness

                    child_topic_ctl = TOPIC_SET_DEVICE_CTL.format(
                        prefix=self.topic_prefix, device_name=child_entity.device_name
                    )
                    payload = {"lightness": current_child_lightness, "temperature": target_color_temp}
                    await self.mqtt_client.async_publish(child_topic_ctl, payload, qos=1)

                    child_entity._last_known_color_temp = target_color_temp
                    mock_data = {"onoff": target_onoff, "temperature": target_color_temp, "lightness": current_child_lightness}
                    if child_entity.coordinator.data:
                        child_entity.coordinator.data.update(mock_data)
                    else:
                        child_entity.coordinator.data = mock_data
                    child_entity.async_write_ha_state()
        
        # Case 3: Simple Turn On command with no arguments
        else:
            await self.mqtt_client.async_publish(self._power_topic, True, qos=1)
            
            # Cascade "ON" state down to children using their existing individual brightness values
            for entity_id in self.tracking_child_ids:
                child_entity = self.hass.data["light"].get_entity(entity_id)
                if child_entity and isinstance(child_entity, HafeleLightEntity):
                    current_child_lightness = 1.0
                    if child_entity._last_known_lightness is not None:
                        current_child_lightness = child_entity._last_known_lightness
                    elif child_entity.coordinator.data and "lightness" in child_entity.coordinator.data:
                        current_child_lightness = child_entity.coordinator.data["lightness"]

                    mock_data = {"onoff": 1, "lightness": current_child_lightness}
                    if child_entity.coordinator.data:
                        child_entity.coordinator.data.update(mock_data)
                    else:
                        child_entity.coordinator.data = mock_data
                    
                    child_entity.async_write_ha_state()

        self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send single broadcast power instruction targeting off state and instantly clear children models."""
        _LOGGER.info("Group %s (%s) turning off", self.name, self.group_addr)
        await self.mqtt_client.async_publish(self._power_topic, False, qos=1)
        
        # CASCADE DOWNWARD
        for entity_id in self.tracking_child_ids:
            child_entity = self.hass.data["light"].get_entity(entity_id)
            if child_entity and isinstance(child_entity, HafeleLightEntity):
                mock_data = {"onoff": 0, "lightness": 0.0}
                if child_entity.coordinator.data:
                    child_entity.coordinator.data.update(mock_data)
                else:
                    child_entity.coordinator.data = mock_data
                child_entity.async_write_ha_state()

        self._attr_is_on = False
        self.async_write_ha_state()
