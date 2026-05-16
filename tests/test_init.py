"""Tests for integration setup."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.hafele_local_mqtt import async_setup_entry, async_unload_entry
from custom_components.hafele_local_mqtt.const import (
    CONF_MQTT_BROKER,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_USE_HA_MQTT,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntry


@pytest.mark.asyncio
async def test_setup_entry(mock_hass, mock_config_entry):
    """Test integration setup."""
    with patch(
        "custom_components.hafele_local_mqtt.HafeleMQTTClient"
    ) as mock_mqtt_class, patch(
        "custom_components.hafele_local_mqtt.HafeleDiscovery"
    ) as mock_discovery_class:
        
        mock_mqtt = mock_mqtt_class.return_value
        mock_mqtt.async_connect = AsyncMock()
        
        mock_discovery = mock_discovery_class.return_value
        mock_discovery.async_start = AsyncMock()
        
        result = await async_setup_entry(mock_hass, mock_config_entry)
        
        assert result is True
        assert DOMAIN in mock_hass.data
        assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]
        mock_mqtt.async_connect.assert_called_once()
        mock_discovery.async_start.assert_called_once()


@pytest.mark.asyncio
async def test_setup_entry_uses_direct_broker_when_mqtt_broker_configured(mock_hass):
    """Broker credentials are passed when config entry stores a direct MQTT broker."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "direct_mqtt_entry"
    entry.data = {
        "topic_prefix": "Mesh",
        "polling_interval": 30,
        "polling_timeout": 3,
        "polling_mode": "normal",
        CONF_MQTT_BROKER: "localhost",
        CONF_MQTT_PORT: 1883,
        CONF_MQTT_USERNAME: "haefele_mesh_abc",
        CONF_MQTT_PASSWORD: "secret",
    }
    entry.async_on_unload = MagicMock()

    with patch(
        "custom_components.hafele_local_mqtt.HafeleMQTTClient"
    ) as mock_mqtt_class, patch(
        "custom_components.hafele_local_mqtt.HafeleDiscovery"
    ) as mock_discovery_class:
        mock_mqtt_class.return_value.async_connect = AsyncMock()
        mock_discovery_class.return_value.async_start = AsyncMock()
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

        await async_setup_entry(mock_hass, entry)

    mock_mqtt_class.assert_called_once_with(
        mock_hass,
        "Mesh",
        broker="localhost",
        port=1883,
        username="haefele_mesh_abc",
        password="secret",
    )


@pytest.mark.asyncio
async def test_migrate_entry_sets_use_ha_mqtt_and_unique_ids(mock_hass):
    """Migration v2 enables direct MQTT and renames legacy light unique IDs."""
    entry = MagicMock(spec=ConfigEntry)
    entry.version = 1
    entry.entry_id = "migrate_entry"
    entry.data = {CONF_MQTT_BROKER: "localhost", CONF_MQTT_PORT: 1883}

    legacy_entity = MagicMock()
    legacy_entity.unique_id = "31_mqtt"
    legacy_entity.platform = DOMAIN
    legacy_entity.domain = "light"
    legacy_entity.entity_id = "light.kitchen"

    ent_reg = MagicMock()
    ent_reg.async_get_entity_id = MagicMock(return_value=None)

    with patch(
        "custom_components.hafele_local_mqtt.er.async_get",
        return_value=ent_reg,
    ), patch(
        "custom_components.hafele_local_mqtt.er.async_entries_for_config_entry",
        return_value=[legacy_entity],
    ):
        from custom_components.hafele_local_mqtt import async_migrate_entry

        mock_hass.config_entries.async_update_entry = MagicMock()
        result = await async_migrate_entry(mock_hass, entry)

    assert result is True
    mock_hass.config_entries.async_update_entry.assert_called_once()
    updated = mock_hass.config_entries.async_update_entry.call_args
    assert updated.kwargs["data"][CONF_USE_HA_MQTT] is False
    ent_reg.async_update_entity.assert_called_once_with(
        "light.kitchen", new_unique_id="hafele_31"
    )


@pytest.mark.asyncio
async def test_unload_entry(mock_hass, mock_config_entry):
    """Test integration unload."""
    mock_discovery = MagicMock()
    mock_discovery.async_stop = AsyncMock()
    mock_mqtt = MagicMock()
    mock_mqtt.async_disconnect = AsyncMock()
    mock_hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "mqtt_client": mock_mqtt,
            "discovery": mock_discovery,
        }
    }
    mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    result = await async_unload_entry(mock_hass, mock_config_entry)
    assert result is True
    mock_discovery.async_stop.assert_called_once()
    mock_mqtt.async_disconnect.assert_called_once()
