"""Group light entities for Hafele Local MQTT."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    DOMAIN,
    TOPIC_SET_GROUP_CTL,
    TOPIC_SET_GROUP_LIGHTNESS,
    TOPIC_SET_GROUP_POWER,
)
from .mqtt_client import HafeleMQTTClient

_LOGGER = logging.getLogger(__name__)

GROUP_DISPLAY_NAME_OVERRIDES: dict[str, str] = {
    # Internal Hafele group name -> user-facing display name
    "TOS_Internal_All": "All",
}


def _display_name_for_group(group_name: str) -> str:
    """Return user-facing display name for a group."""
    return GROUP_DISPLAY_NAME_OVERRIDES.get(group_name, group_name)


class HafeleGroupLightEntity(LightEntity):
    """Representation of a Hafele group light."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        mqtt_client: HafeleMQTTClient,
        topic_prefix: str,
        group_addr: int,
        group_info: dict[str, Any],
        member_entity_ids: Iterable[str],
    ) -> None:
        """Initialize the group light."""
        self._hass = hass
        self._mqtt_client = mqtt_client
        self._topic_prefix = topic_prefix
        self._group_addr = group_addr

        internal_name: str = group_info.get("group_name", f"group_{group_addr}")
        self._group_name_internal = internal_name
        display_name = _display_name_for_group(internal_name)
        self._member_entity_ids = list(member_entity_ids)

        # Optimistic state after commands, cleared after a short delay
        self._optimistic_is_on: bool | None = None
        self._optimistic_brightness: int | None = None
        self._optimistic_color_temp: int | None = None

        self._attr_unique_id = f"group_{group_addr}_mqtt"
        self._attr_name = display_name
        self._attr_has_entity_name = True

        # Device info – virtual device for the group
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"group_{group_addr}")},
            name=display_name,
            manufacturer="Hafele",
            model="Local MQTT Group",
        )

        # Track member state changes so we can refresh our computed state
        async_track_state_change_event(
            self._hass, self._member_entity_ids, self._handle_member_state_change
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {
            "group_main_addr": self._group_addr,
            "group_name_internal": self._group_name_internal,
            "member_entity_ids": list(self._member_entity_ids),
        }

    # ---- Helper methods for reading member states ---------------------------------

    def _iter_member_states(self):
        """Yield (entity_id, state) tuples for members with a valid state."""
        for entity_id in self._member_entity_ids:
            state = self._hass.states.get(entity_id)
            if state is not None:
                yield entity_id, state

    # ---- Light properties ---------------------------------------------------------

    @property
    def is_on(self) -> bool | None:
        """Return if the group light is on.

        Group ON: any member is on.
        Group OFF: at least one member is off and none are on.
        Unknown: all members are in a non-on/off state (e.g. unavailable).
        """
        if self._optimistic_is_on is not None:
            return self._optimistic_is_on

        any_on = False
        any_off = False
        for _, state in self._iter_member_states():
            if state.state == "on":
                any_on = True
            elif state.state == "off":
                any_off = True

        if any_on:
            return True
        if any_off:
            return False
        # All members are in non-on/off state (or there are no members)
        return None

    @property
    def brightness(self) -> int | None:
        """Return brightness based on max of member brightnesses."""
        if self._optimistic_brightness is not None:
            return self._optimistic_brightness

        max_brightness: int | None = None
        for _, state in self._iter_member_states():
            value = state.attributes.get("brightness")
            if isinstance(value, (int, float)):
                value_int = int(value)
                if max_brightness is None or value_int > max_brightness:
                    max_brightness = value_int

        return max_brightness

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return an aggregate color temperature if any member supports it."""
        if self._optimistic_color_temp is not None:
            return self._optimistic_color_temp

        temps: list[int] = []
        for _, state in self._iter_member_states():
            temp = state.attributes.get("color_temp_kelvin")
            if isinstance(temp, (int, float)):
                temps.append(int(temp))

        if not temps:
            return None

        # Simple average for now
        return int(sum(temps) / len(temps))

    @property
    def supported_color_modes(self) -> set[ColorMode] | None:
        """Aggregate supported color modes across members.

        Always support BRIGHTNESS; add COLOR_TEMP if any member supports it.
        """
        supports_color_temp = False
        for _, state in self._iter_member_states():
            modes = state.attributes.get("supported_color_modes") or []
            if isinstance(modes, (list, set, tuple)):
                if any(
                    str(m).lower() in ("color_temp", ColorMode.COLOR_TEMP)
                    for m in modes
                ):
                    supports_color_temp = True
                    break

        if supports_color_temp:
            return {ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP}
        return {ColorMode.BRIGHTNESS}

    @property
    def color_mode(self) -> ColorMode | None:
        """Return the current primary color mode."""
        # Prefer COLOR_TEMP if any member is currently using it, otherwise BRIGHTNESS
        for _, state in self._iter_member_states():
            mode = state.attributes.get("color_mode")
            if str(mode).lower() in ("color_temp", ColorMode.COLOR_TEMP):
                return ColorMode.COLOR_TEMP
        return ColorMode.BRIGHTNESS

    @property
    def min_color_temp_kelvin(self) -> int | None:
        """Return min supported color temperature across CT-capable members."""
        mins: list[int] = []
        for _, state in self._iter_member_states():
            value = state.attributes.get("min_color_temp_kelvin")
            if isinstance(value, (int, float)):
                mins.append(int(value))
        return min(mins) if mins else None

    @property
    def max_color_temp_kelvin(self) -> int | None:
        """Return max supported color temperature across CT-capable members."""
        maxs: list[int] = []
        for _, state in self._iter_member_states():
            value = state.attributes.get("max_color_temp_kelvin")
            if isinstance(value, (int, float)):
                maxs.append(int(value))
        return max(maxs) if maxs else None

    # ---- Handle member state changes ---------------------------------------------

    @callback
    def _handle_member_state_change(self, event) -> None:
        """Handle member state change by recomputing group state."""
        _LOGGER.debug(
            "Member state changed for group %s (%s), recomputing state",
            self._group_name_internal,
            self.entity_id,
        )
        # Clear optimistic overrides once real states arrive
        self._optimistic_is_on = None
        self._optimistic_brightness = None
        self._optimistic_color_temp = None
        self.async_write_ha_state()

    async def _schedule_clear_optimistic(self) -> None:
        """Clear optimistic state after a short delay."""
        await asyncio.sleep(5.0)
        self._optimistic_is_on = None
        self._optimistic_brightness = None
        self._optimistic_color_temp = None
        self.async_write_ha_state()

    # ---- Commands ----------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the group on."""
        internal_name = self._group_name_internal

        # Determine desired brightness (0-255) and 0-1 lightness
        brightness: int | None = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            # If any member has a brightness, use max as starting point, else full
            current_brightness = self.brightness
            brightness = current_brightness if current_brightness is not None else 255
        lightness = round(brightness / 255.0, 2)

        # Determine desired color temperature if supported/requested
        color_temp: int | None = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        if color_temp is None:
            color_temp = self.color_temp_kelvin

        has_color_temp_support = ColorMode.COLOR_TEMP in (self.supported_color_modes or set())

        if has_color_temp_support and color_temp is not None:
            # Use CTL for CT-capable groups
            payload = {
                "lightness": lightness,
                "temperature": color_temp,
            }
            topic = TOPIC_SET_GROUP_CTL.format(
                prefix=self._topic_prefix, group_name=internal_name
            )
            _LOGGER.info(
                "Turning ON group %s via CTL: payload=%s topic=%s",
                internal_name,
                payload,
                topic,
            )
            await self._mqtt_client.async_publish(topic, payload, qos=1)
        else:
            # Use power + lightness only
            power_payload = {"onOff": "on"}
            power_topic = TOPIC_SET_GROUP_POWER.format(
                prefix=self._topic_prefix, group_name=internal_name
            )
            _LOGGER.info(
                "Turning ON group %s via power: payload=%s topic=%s",
                internal_name,
                power_payload,
                power_topic,
            )
            await self._mqtt_client.async_publish(power_topic, power_payload, qos=1)

            lightness_payload = {"lightness": lightness}
            lightness_topic = TOPIC_SET_GROUP_LIGHTNESS.format(
                prefix=self._topic_prefix, group_name=internal_name
            )
            _LOGGER.info(
                "Setting group %s lightness: payload=%s topic=%s",
                internal_name,
                lightness_payload,
                lightness_topic,
            )
            await self._mqtt_client.async_publish(
                lightness_topic, lightness_payload, qos=1
            )

        # Optimistic update
        self._optimistic_is_on = True
        self._optimistic_brightness = brightness
        if color_temp is not None:
            self._optimistic_color_temp = color_temp
        self.async_write_ha_state()
        self._hass.async_create_task(self._schedule_clear_optimistic())

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the group off."""
        internal_name = self._group_name_internal
        power_payload = {"onOff": "off"}
        power_topic = TOPIC_SET_GROUP_POWER.format(
            prefix=self._topic_prefix, group_name=internal_name
        )
        _LOGGER.info(
            "Turning OFF group %s: payload=%s topic=%s",
            internal_name,
            power_payload,
            power_topic,
        )
        await self._mqtt_client.async_publish(power_topic, power_payload, qos=1)

        # Optimistic update
        self._optimistic_is_on = False
        # Preserve last brightness/color_temp for when turned on again
        self.async_write_ha_state()
        self._hass.async_create_task(self._schedule_clear_optimistic())

