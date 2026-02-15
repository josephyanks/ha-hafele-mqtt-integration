"""Tests for Hafele MQTT client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from custom_components.hafele_local_mqtt.mqtt_client import HafeleMQTTClient


@pytest.mark.asyncio
async def test_mqtt_client_init_ha_mqtt(mock_hass):
    """Test MQTT client initialization with HA MQTT."""
    client = HafeleMQTTClient(mock_hass, "hafele")
    assert client._use_ha_mqtt is True
    assert client.topic_prefix == "hafele"


@pytest.mark.asyncio
async def test_mqtt_client_init_direct(mock_hass):
    """Test MQTT client initialization with direct connection."""
    client = HafeleMQTTClient(
        mock_hass, "hafele", broker="localhost", port=1883
    )
    assert client._use_ha_mqtt is False
    assert client._broker == "localhost"
    assert client._port == 1883


@pytest.mark.asyncio
@patch("custom_components.hafele_local_mqtt.mqtt_client.mqtt")
async def test_mqtt_client_connect_ha_mqtt(mock_mqtt, mock_hass):
    """Test connecting via HA MQTT."""
    mock_mqtt.is_connected.return_value = True
    
    client = HafeleMQTTClient(mock_hass, "hafele")
    await client.async_connect()
    
    # HA MQTT path doesn't set _connected (only direct connection does)
    assert not client._use_ha_mqtt or mock_mqtt.is_connected.called


@pytest.mark.asyncio
@patch("custom_components.hafele_local_mqtt.mqtt_client.mqtt")
async def test_mqtt_client_connect_ha_mqtt_not_connected(mock_mqtt, mock_hass):
    """Test connecting via HA MQTT when not connected."""
    mock_mqtt.is_connected.return_value = False
    
    client = HafeleMQTTClient(mock_hass, "hafele")
    
    with pytest.raises(ConnectionError):
        await client.async_connect()


@pytest.mark.asyncio
async def test_mqtt_client_publish_dict(mock_hass, mock_mqtt_client):
    """Test publishing dict payload."""
    with patch("custom_components.hafele_local_mqtt.mqtt_client.mqtt") as mock_mqtt:
        mock_mqtt.is_connected.return_value = True
        mock_mqtt.async_publish = AsyncMock()
        
        client = HafeleMQTTClient(mock_hass, "hafele")
        await client.async_connect()
        
        payload = {"lightness": 0.5}
        await client.async_publish("test/topic", payload)
        
        # Verify JSON serialization (async_publish(hass, topic, payload, ...))
        call_args = mock_mqtt.async_publish.call_args
        assert call_args[0][2] == json.dumps(payload)


@pytest.mark.asyncio
async def test_mqtt_client_publish_bool(mock_hass, mock_mqtt_client):
    """Test publishing boolean payload."""
    with patch("custom_components.hafele_local_mqtt.mqtt_client.mqtt") as mock_mqtt:
        mock_mqtt.is_connected.return_value = True
        mock_mqtt.async_publish = AsyncMock()
        
        client = HafeleMQTTClient(mock_hass, "hafele")
        await client.async_connect()
        
        await client.async_publish("test/topic", True)
        
        call_args = mock_mqtt.async_publish.call_args
        assert call_args[0][2] == "true"


@pytest.mark.asyncio
async def test_mqtt_client_subscribe(mock_hass):
    """Test subscribing to topic."""
    with patch("custom_components.hafele_local_mqtt.mqtt_client.mqtt") as mock_mqtt:
        mock_mqtt.is_connected.return_value = True
        mock_mqtt.async_subscribe = AsyncMock(return_value=MagicMock())
        
        client = HafeleMQTTClient(mock_hass, "hafele")
        await client.async_connect()
        
        callback = MagicMock()
        unsubscribe = await client.async_subscribe("test/topic", callback)
        
        assert unsubscribe is not None
        assert "test/topic" in client._subscriptions
