"""Tests for Hafele group light entities."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.light import ColorMode

from custom_components.hafele_local_mqtt.hafele_group import (
    HafeleGroupLightEntity,
    GROUP_DISPLAY_NAME_OVERRIDES,
)
from custom_components.hafele_local_mqtt.const import (
    TOPIC_SET_GROUP_CTL,
    TOPIC_SET_GROUP_LIGHTNESS,
    TOPIC_SET_GROUP_POWER,
)


@pytest.mark.asyncio
async def test_group_display_name_override_and_basic_state(mock_hass, mock_mqtt_client):
    """TOS_Internal_All should be exposed as 'All' and aggregate member on/off."""
    # Provide a mock states helper on hass
    mock_hass.states = MagicMock()

    def get_state(entity_id):
        state = MagicMock()
        # One member on, one off
        if entity_id == "light.member1":
            state.state = "off"
        else:
            state.state = "on"
        state.attributes = {}
        return state

    mock_hass.states.get.side_effect = get_state

    group_info = {
        "group_name": "TOS_Internal_All",
        "devices": [1, 2],
        "group_main_addr": 49185,
    }
    entity = HafeleGroupLightEntity(
        mock_hass,
        mock_mqtt_client,
        "hafele",
        group_addr=49185,
        group_info=group_info,
        member_entity_ids=["light.member1", "light.member2"],
    )

    # Internal mapping should exist
    assert GROUP_DISPLAY_NAME_OVERRIDES["TOS_Internal_All"] == "All"
    # Name exposed to HA should be the display name
    assert entity.name == "All"
    # With one member on, group is considered on
    assert entity.is_on is True
    # Extra attributes should contain internal name and addr
    attrs = entity.extra_state_attributes
    assert attrs["group_main_addr"] == 49185
    assert attrs["group_name_internal"] == "TOS_Internal_All"


@pytest.mark.asyncio
async def test_group_on_off_unknown_handling(mock_hass, mock_mqtt_client):
    """Group should only be unknown when all members are non-on/off."""
    mock_hass.states = MagicMock()

    # Case 1: one off, one unavailable -> should be OFF (not unknown)
    def get_state_mixed(entity_id):
        state = MagicMock()
        if entity_id == "light.off":
            state.state = "off"
        else:
            state.state = "unavailable"
        state.attributes = {}
        return state

    mock_hass.states.get.side_effect = get_state_mixed

    group_info = {"group_name": "MixedGroup", "devices": [1, 2], "group_main_addr": 100}
    entity = HafeleGroupLightEntity(
        mock_hass,
        mock_mqtt_client,
        "hafele",
        group_addr=100,
        group_info=group_info,
        member_entity_ids=["light.off", "light.unavailable"],
    )

    assert entity.is_on is False

    # Case 2: all unavailable -> should be unknown
    def get_state_all_unknown(entity_id):
        state = MagicMock()
        state.state = "unavailable"
        state.attributes = {}
        return state

    mock_hass.states.get.side_effect = get_state_all_unknown
    assert entity.is_on is None


@pytest.mark.asyncio
async def test_group_brightness_and_color_temp_aggregation(mock_hass, mock_mqtt_client):
    """Group brightness uses max member brightness; color temp uses average."""
    mock_hass.states = MagicMock()

    def get_state(entity_id):
        state = MagicMock()
        state.state = "on"
        if entity_id == "light.a":
            state.attributes = {
                "brightness": 100,
                "color_temp_kelvin": 2700,
            }
        else:
            state.attributes = {
                "brightness": 200,
                "color_temp_kelvin": 3300,
            }
        return state

    mock_hass.states.get.side_effect = get_state

    group_info = {"group_name": "Kitchen", "devices": [10, 11], "group_main_addr": 1}
    entity = HafeleGroupLightEntity(
        mock_hass,
        mock_mqtt_client,
        "hafele",
        group_addr=1,
        group_info=group_info,
        member_entity_ids=["light.a", "light.b"],
    )

    assert entity.brightness == 200  # max of 100 and 200
    # Average of 2700 and 3300
    assert entity.color_temp_kelvin == 3000


@pytest.mark.asyncio
async def test_group_supported_color_modes_and_min_max_temp(mock_hass, mock_mqtt_client):
    """Group exposes COLOR_TEMP only if any member supports it and aggregates min/max CT."""
    mock_hass.states = MagicMock()

    def get_state(entity_id):
        state = MagicMock()
        state.state = "on"
        if entity_id == "light.ct":
            state.attributes = {
                "supported_color_modes": [ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP],
                "min_color_temp_kelvin": 2700,
                "max_color_temp_kelvin": 5000,
            }
        else:
            state.attributes = {
                "supported_color_modes": [ColorMode.BRIGHTNESS],
                "min_color_temp_kelvin": 3000,
                "max_color_temp_kelvin": 4000,
            }
        return state

    mock_hass.states.get.side_effect = get_state

    group_info = {"group_name": "GroupWithCT", "devices": [1, 2], "group_main_addr": 2}
    entity = HafeleGroupLightEntity(
        mock_hass,
        mock_mqtt_client,
        "hafele",
        group_addr=2,
        group_info=group_info,
        member_entity_ids=["light.ct", "light.brightness_only"],
    )

    modes = entity.supported_color_modes
    assert ColorMode.BRIGHTNESS in modes
    assert ColorMode.COLOR_TEMP in modes
    # min across members is 2700, max is 5000
    assert entity.min_color_temp_kelvin == 2700
    assert entity.max_color_temp_kelvin == 5000


@pytest.mark.asyncio
async def test_group_turn_on_uses_ctl_when_supported(mock_hass, mock_mqtt_client):
    """When group supports CT, async_turn_on uses CTL topic."""
    mock_hass.states = MagicMock()

    def get_state(entity_id):
        state = MagicMock()
        state.state = "on"
        state.attributes = {
            "supported_color_modes": [ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP],
            "brightness": 128,
            "color_temp_kelvin": 3200,
        }
        return state

    mock_hass.states.get.side_effect = get_state

    group_info = {"group_name": "CTGroup", "devices": [1], "group_main_addr": 3}
    entity = HafeleGroupLightEntity(
        mock_hass,
        mock_mqtt_client,
        "hafele",
        group_addr=3,
        group_info=group_info,
        member_entity_ids=["light.ct"],
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await entity.async_turn_on(brightness=128, color_temp_kelvin=3500)

    # Expect a single CTL publish
    mock_mqtt_client.async_publish.assert_called_once()
    topic, payload, *_ = mock_mqtt_client.async_publish.call_args[0]
    expected_topic = TOPIC_SET_GROUP_CTL.format(prefix="hafele", group_name="CTGroup")
    assert topic == expected_topic
    assert payload["lightness"] == pytest.approx(0.5, rel=0.01)
    assert payload["temperature"] == 3500
    # Optimistic state applied
    assert entity.is_on is True
    assert entity.brightness == 128


@pytest.mark.asyncio
async def test_group_turn_on_uses_power_and_lightness_without_ct(mock_hass, mock_mqtt_client):
    """When group does not support CT, async_turn_on uses power + lightness topics."""
    mock_hass.states = MagicMock()

    def get_state(entity_id):
        state = MagicMock()
        state.state = "off"
        state.attributes = {
            "supported_color_modes": [ColorMode.BRIGHTNESS],
        }
        return state

    mock_hass.states.get.side_effect = get_state

    group_info = {"group_name": "SimpleGroup", "devices": [1], "group_main_addr": 4}
    entity = HafeleGroupLightEntity(
        mock_hass,
        mock_mqtt_client,
        "hafele",
        group_addr=4,
        group_info=group_info,
        member_entity_ids=["light.simple"],
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await entity.async_turn_on(brightness=255)

    # Should publish to power and lightness topics
    assert mock_mqtt_client.async_publish.call_count == 2
    topics = [call[0][0] for call in mock_mqtt_client.async_publish.call_args_list]
    expected_power = TOPIC_SET_GROUP_POWER.format(
        prefix="hafele", group_name="SimpleGroup"
    )
    expected_lightness = TOPIC_SET_GROUP_LIGHTNESS.format(
        prefix="hafele", group_name="SimpleGroup"
    )
    assert expected_power in topics
    assert expected_lightness in topics


@pytest.mark.asyncio
async def test_group_turn_off(mock_hass, mock_mqtt_client):
    """async_turn_off publishes to group power topic and updates optimistic state."""
    mock_hass.states = MagicMock()
    mock_hass.states.get.return_value = None

    group_info = {"group_name": "OffGroup", "devices": [1], "group_main_addr": 5}
    entity = HafeleGroupLightEntity(
        mock_hass,
        mock_mqtt_client,
        "hafele",
        group_addr=5,
        group_info=group_info,
        member_entity_ids=["light.off"],
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await entity.async_turn_off()

    mock_mqtt_client.async_publish.assert_called_once()
    topic, payload, *_ = mock_mqtt_client.async_publish.call_args[0]
    expected_topic = TOPIC_SET_GROUP_POWER.format(prefix="hafele", group_name="OffGroup")
    assert topic == expected_topic
    assert payload == {"onOff": "off"}
    assert entity.is_on is False

