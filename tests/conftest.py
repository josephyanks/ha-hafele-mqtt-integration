"""Test fixtures for Hafele Local MQTT integration."""
# Root conftest.py installs HA mocks before this runs.

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from typing import Any

from custom_components.hafele_local_mqtt.const import DOMAIN

# Use Mock types for type hints
HomeAssistant = Mock
ConfigEntry = Mock
EntityRegistry = Mock
HafeleMQTTClient = Mock
HafeleDiscovery = Mock


@pytest.fixture
def mock_hass():
    """Mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {DOMAIN: {}}
    hass.bus = MagicMock()
    hass.bus.async_fire = AsyncMock()
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    hass.bus.async_listen_once = MagicMock(return_value=MagicMock())
    hass.async_create_task = AsyncMock()
    hass.async_block_till_done = AsyncMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    return hass


@pytest.fixture
def mock_mqtt_client():
    """Mock MQTT client."""
    client = MagicMock(spec=HafeleMQTTClient)
    client.async_connect = AsyncMock()
    client.async_disconnect = AsyncMock()
    client.async_subscribe = AsyncMock(return_value=AsyncMock())
    client.async_publish = AsyncMock()
    client.async_unsubscribe = AsyncMock()
    client.topic_prefix = "hafele"
    return client


@pytest.fixture
def mock_discovery():
    """Mock discovery instance."""
    discovery = MagicMock(spec=HafeleDiscovery)
    discovery.get_all_devices = MagicMock(return_value={})
    discovery.get_device = MagicMock(return_value=None)
    discovery.get_all_groups = MagicMock(return_value={})
    discovery.get_all_scenes = MagicMock(return_value={})
    discovery.async_start = AsyncMock()
    discovery.async_stop = AsyncMock()
    return discovery


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {
        "topic_prefix": "hafele",
        "polling_interval": 30,
        "polling_timeout": 3,
        "polling_mode": "normal",
        "use_ha_mqtt": True,
    }
    entry.async_on_unload = MagicMock()
    return entry


@pytest.fixture
def mock_entity_registry():
    """Mock entity registry."""
    registry = MagicMock(spec=EntityRegistry)
    registry.async_get_entity_id = MagicMock(return_value=None)
    registry.async_get_or_create = MagicMock()
    return registry


@pytest.fixture
def sample_device_info():
    """Sample device info for testing."""
    return {
        "device_name": "Test Light",
        "device_addr": 123,
        "device_types": ["Light"],
        "location": "Living Room",
    }


@pytest.fixture
def sample_multiwhite_device_info():
    """Sample multiwhite device info for testing."""
    return {
        "device_name": "Test Multiwhite",
        "device_addr": 456,
        "device_types": ["Multiwhite"],
        "location": "Kitchen",
    }
