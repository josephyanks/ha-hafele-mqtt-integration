"""Tests for HafeleMeshLightGroup (PR #18 group control via MQTT)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from tests.conftest import schedule_ha_task

from custom_components.hafele_local_mqtt.light import (
    HafeleLightCoordinator,
    HafeleLightEntity,
    HafeleMeshLightGroup,
)
from custom_components.hafele_local_mqtt.const import (
    TOPIC_SET_GROUP_CTL,
    TOPIC_SET_GROUP_LIGHTNESS,
    TOPIC_SET_GROUP_POWER,
)


@pytest.fixture
def mock_coordinator():
    """Mock light coordinator for child cascade tests."""
    coordinator = MagicMock(spec=HafeleLightCoordinator)
    coordinator.data = {}
    coordinator.hass = MagicMock()
    coordinator.hass.async_create_task = MagicMock(side_effect=schedule_ha_task)
    return coordinator


@pytest.fixture
def mock_mqtt_client():
    """Mock MQTT client for group tests."""
    client = MagicMock()
    client.async_publish = AsyncMock()
    return client


@pytest.fixture
def mesh_group(mock_mqtt_client):
    """HafeleMeshLightGroup with no child entities."""
    group = HafeleMeshLightGroup(
        group_addr=10,
        group_name="Kitchen",
        child_entity_ids=["light.kitchen_1", "light.kitchen_2"],
        mqtt_client=mock_mqtt_client,
        topic_prefix="Mesh",
    )
    group.hass = MagicMock()
    group.hass.data = {"light": MagicMock()}
    group.hass.data["light"].get_entity = MagicMock(return_value=None)
    return group


def test_mesh_group_unique_id_and_topics(mesh_group):
    """Group entity uses stable unique_id and correct MQTT topic templates."""
    assert mesh_group.unique_id == "hafele_group_10"
    assert mesh_group.name == "Kitchen"
    assert mesh_group.tracking_child_ids == ["light.kitchen_1", "light.kitchen_2"]
    assert mesh_group._power_topic == TOPIC_SET_GROUP_POWER.format(
        prefix="Mesh", group_name="Kitchen"
    )
    assert mesh_group._ctl_topic == TOPIC_SET_GROUP_CTL.format(
        prefix="Mesh", group_name="Kitchen"
    )


@pytest.mark.asyncio
async def test_mesh_group_turn_on_power_only(mesh_group, mock_mqtt_client):
    """turn_on without brightness sends group power on."""
    await mesh_group.async_turn_on()

    mock_mqtt_client.async_publish.assert_awaited_once_with(
        mesh_group._power_topic, True, qos=1
    )
    assert mesh_group._attr_is_on is True


@pytest.mark.asyncio
async def test_mesh_group_turn_on_brightness_path(mesh_group, mock_mqtt_client):
    """turn_on with brightness sends power and lightness topics."""
    await mesh_group.async_turn_on(brightness=128)

    topics = [call.args[0] for call in mock_mqtt_client.async_publish.await_args_list]
    assert mesh_group._power_topic in topics
    assert mesh_group._lightness_topic in topics
    assert mesh_group._attr_brightness == 128


@pytest.mark.asyncio
async def test_mesh_group_turn_on_ctl_path(mesh_group, mock_mqtt_client):
    """turn_on with color temperature uses single CTL payload."""
    await mesh_group.async_turn_on(brightness=255, color_temp_kelvin=4000)

    mock_mqtt_client.async_publish.assert_awaited_once()
    call = mock_mqtt_client.async_publish.await_args
    assert call.args[0] == mesh_group._ctl_topic
    assert call.args[1] == {"lightness": 1.0, "temperature": 4000}
    assert call.kwargs == {"qos": 1}


@pytest.mark.asyncio
async def test_mesh_group_turn_on_clamps_color_temp(mesh_group, mock_mqtt_client):
    """Color temperature is clamped to the supported kelvin range."""
    await mesh_group.async_turn_on(color_temp_kelvin=6000)

    payload = mock_mqtt_client.async_publish.await_args.args[1]
    assert payload["temperature"] == 5000


@pytest.mark.asyncio
async def test_mesh_group_turn_on_cascades_to_children(
    mesh_group, mock_mqtt_client, mock_coordinator, sample_device_info
):
    """Group commands optimistically update tracked child light entities."""
    child = HafeleLightEntity(
        mock_coordinator, 1, sample_device_info, mock_mqtt_client, "Mesh"
    )
    child.async_write_ha_state = MagicMock()
    mock_coordinator.data = {}

    mesh_group.hass.data["light"].get_entity = lambda eid: (
        child if eid == "light.kitchen_1" else None
    )
    mesh_group.tracking_child_ids = ["light.kitchen_1"]

    await mesh_group.async_turn_on(brightness=128)

    assert mock_coordinator.data["onoff"] == 1
    assert mock_coordinator.data["lightness"] == 0.51
    child.async_write_ha_state.assert_called()


@pytest.mark.asyncio
async def test_mesh_group_turn_off(mesh_group, mock_mqtt_client):
    """turn_off sends group power false."""
    await mesh_group.async_turn_off()

    mock_mqtt_client.async_publish.assert_awaited_once_with(
        mesh_group._power_topic, False, qos=1
    )
    assert mesh_group._attr_is_on is False


@pytest.mark.asyncio
async def test_mesh_group_turn_off_cascades_to_children(
    mesh_group, mock_mqtt_client, mock_coordinator, sample_device_info
):
    """Group off clears child coordinator state."""
    child = HafeleLightEntity(
        mock_coordinator, 1, sample_device_info, mock_mqtt_client, "Mesh"
    )
    child.async_write_ha_state = MagicMock()
    mock_coordinator.data = {"onoff": 1, "lightness": 0.8}

    mesh_group.hass.data["light"].get_entity = lambda eid: (
        child if eid == "light.kitchen_1" else None
    )
    mesh_group.tracking_child_ids = ["light.kitchen_1"]

    await mesh_group.async_turn_off()

    assert mock_coordinator.data["onoff"] == 0
    assert mock_coordinator.data["lightness"] == 0.0


def test_mesh_group_async_update_group_state_from_children(mesh_group):
    """Parent group refresh is triggered from child state updates."""
    mesh_group.async_update_ha_state = MagicMock()
    mesh_group.async_update_group_state_from_children()
    mesh_group.async_update_ha_state.assert_called_once_with(True)
