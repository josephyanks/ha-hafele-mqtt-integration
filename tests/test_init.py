"""Tests for integration setup."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.hafele_local_mqtt import async_setup_entry, async_unload_entry
from custom_components.hafele_local_mqtt.const import DOMAIN


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
