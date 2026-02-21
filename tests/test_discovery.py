"""Tests for Hafele discovery."""
import pytest
from unittest.mock import AsyncMock, MagicMock
import json

from custom_components.hafele_local_mqtt.discovery import HafeleDiscovery
from custom_components.hafele_local_mqtt.const import (
    EVENT_DEVICES_UPDATED,
    TOPIC_DISCOVERY_LIGHTS,
    TOPIC_DISCOVERY_GROUPS,
    TOPIC_DISCOVERY_SCENES,
)


@pytest.mark.asyncio
async def test_discovery_start(mock_hass, mock_mqtt_client):
    """Test discovery start."""
    discovery = HafeleDiscovery(mock_hass, mock_mqtt_client, "hafele")
    
    await discovery.async_start()
    
    # Verify subscriptions
    assert mock_mqtt_client.async_subscribe.call_count == 3
    assert len(discovery._unsubscribers) == 3


@pytest.mark.asyncio
async def test_discovery_stop(mock_hass, mock_mqtt_client):
    """Test discovery stop."""
    discovery = HafeleDiscovery(mock_hass, mock_mqtt_client, "hafele")
    discovery._unsubscribers = [AsyncMock(), MagicMock()]
    
    await discovery.async_stop()
    
    # Verify unsubscribers were called
    assert len(discovery._unsubscribers) == 0


def test_on_lights_message(mock_hass, mock_mqtt_client):
    """Test lights discovery message handling."""
    discovery = HafeleDiscovery(mock_hass, mock_mqtt_client, "hafele")
    
    lights_data = [
        {"device_addr": 123, "device_name": "Light 1", "device_types": ["Light"]},
        {"device_addr": 456, "device_name": "Light 2", "device_types": ["Light"]},
    ]
    
    discovery._on_lights_message("hafele/lights", lights_data)
    
    # Verify devices were added
    assert len(discovery.devices) == 2
    assert 123 in discovery.devices
    assert 456 in discovery.devices
    assert discovery.devices[123]["device_name"] == "Light 1"
    
    # Verify event was fired
    mock_hass.bus.async_fire.assert_called_once_with(EVENT_DEVICES_UPDATED)


def test_on_lights_message_string_payload(mock_hass, mock_mqtt_client):
    """Test lights discovery with string payload."""
    discovery = HafeleDiscovery(mock_hass, mock_mqtt_client, "hafele")
    
    lights_data = [
        {"device_addr": 123, "device_name": "Light 1"},
    ]
    payload = json.dumps(lights_data)
    
    discovery._on_lights_message("hafele/lights", payload)
    
    assert len(discovery.devices) == 1
    assert 123 in discovery.devices


def test_on_lights_message_invalid_format(mock_hass, mock_mqtt_client):
    """Test lights discovery with invalid format."""
    discovery = HafeleDiscovery(mock_hass, mock_mqtt_client, "hafele")
    
    # Invalid format (not a list)
    discovery._on_lights_message("hafele/lights", {"invalid": "data"})
    
    # Should not add devices
    assert len(discovery.devices) == 0


def test_on_groups_message(mock_hass, mock_mqtt_client):
    """Test groups discovery message handling."""
    discovery = HafeleDiscovery(mock_hass, mock_mqtt_client, "hafele")
    
    groups_data = [
        {"group_main_addr": 1, "group_name": "Group 1"},
        {"group_main_addr": 2, "group_name": "Group 2"},
    ]
    
    discovery._on_groups_message("hafele/groups", groups_data)
    
    assert len(discovery.groups) == 2
    assert 1 in discovery.groups
    assert 2 in discovery.groups


def test_on_scenes_message(mock_hass, mock_mqtt_client):
    """Test scenes discovery message handling."""
    discovery = HafeleDiscovery(mock_hass, mock_mqtt_client, "hafele")
    
    scenes_data = [
        {"scene_id": 1, "scene_name": "Scene 1"},
        {"scene_id": 2, "scene_name": "Scene 2"},
    ]
    
    discovery._on_scenes_message("hafele/scenes", scenes_data)
    
    assert len(discovery.scenes) == 2
    assert 1 in discovery.scenes
    assert 2 in discovery.scenes


def test_get_device(mock_hass, mock_mqtt_client):
    """Test get_device method."""
    discovery = HafeleDiscovery(mock_hass, mock_mqtt_client, "hafele")
    discovery.devices[123] = {"device_name": "Test Light"}
    
    device = discovery.get_device(123)
    assert device is not None
    assert device["device_name"] == "Test Light"
    
    # Non-existent device
    assert discovery.get_device(999) is None


def test_get_all_devices(mock_hass, mock_mqtt_client):
    """Test get_all_devices method."""
    discovery = HafeleDiscovery(mock_hass, mock_mqtt_client, "hafele")
    discovery.devices[123] = {"device_name": "Light 1"}
    discovery.devices[456] = {"device_name": "Light 2"}
    
    all_devices = discovery.get_all_devices()
    assert len(all_devices) == 2
    # Should return a copy
    assert all_devices is not discovery.devices
