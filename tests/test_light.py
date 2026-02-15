"""Tests for the Hafele light platform."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.light import ColorMode

from custom_components.hafele_local_mqtt.light import (
    HafeleLightEntity,
    HafeleLightCoordinator,
    PollPriority,
)
from custom_components.hafele_local_mqtt.const import (
    POLLING_MODE_NORMAL,
    POLLING_MODE_ROTATIONAL,
    TOPIC_GET_DEVICE_LIGHTNESS,
    TOPIC_GET_DEVICE_CTL,
)


@pytest.fixture
def mock_coordinator():
    """Mock coordinator."""
    coordinator = MagicMock(spec=HafeleLightCoordinator)
    coordinator.data = {"onoff": 1, "lightness": 0.5, "temperature": 3000}
    coordinator.async_request_refresh = AsyncMock()
    coordinator.polling_mode = POLLING_MODE_NORMAL
    coordinator.hass = MagicMock()
    coordinator.hass.async_create_task = AsyncMock()
    return coordinator


@pytest.mark.asyncio
async def test_light_is_on(mock_coordinator, sample_device_info, mock_mqtt_client):
    """Test light is_on property."""
    entity = HafeleLightEntity(
        mock_coordinator, 123, sample_device_info, mock_mqtt_client, "hafele"
    )
    
    # Test with onoff = 1
    mock_coordinator.data = {"onoff": 1}
    assert entity.is_on is True
    
    # Test with onoff = 0
    mock_coordinator.data = {"onoff": 0}
    assert entity.is_on is False
    
    # Test with no data
    mock_coordinator.data = None
    assert entity.is_on is None
    
    # Test with onOff (camelCase) format
    mock_coordinator.data = {"onOff": "on"}
    assert entity.is_on is True
    
    mock_coordinator.data = {"onOff": "off"}
    assert entity.is_on is False


@pytest.mark.asyncio
async def test_light_brightness(mock_coordinator, sample_device_info, mock_mqtt_client):
    """Test brightness property."""
    entity = HafeleLightEntity(
        mock_coordinator, 123, sample_device_info, mock_mqtt_client, "hafele"
    )
    
    # Test with lightness = 0.5 (should be 127.5 -> 127)
    mock_coordinator.data = {"lightness": 0.5}
    assert entity.brightness == 127
    
    # Test with lightness = 1.0 (should be 255)
    mock_coordinator.data = {"lightness": 1.0}
    assert entity.brightness == 255
    
    # Test with lightness = 0.0 (should be 0)
    mock_coordinator.data = {"lightness": 0.0}
    assert entity.brightness == 0
    
    # Test with no data
    mock_coordinator.data = None
    assert entity.brightness is None


@pytest.mark.asyncio
async def test_light_color_temp(mock_coordinator, sample_multiwhite_device_info, mock_mqtt_client):
    """Test color temperature property."""
    entity = HafeleLightEntity(
        mock_coordinator, 456, sample_multiwhite_device_info, mock_mqtt_client, "hafele"
    )
    
    # Test with temperature
    mock_coordinator.data = {"temperature": 3000}
    assert entity.color_temp_kelvin == 3000
    
    # Test with temperature out of range (clamped)
    mock_coordinator.data = {"temperature": 2000}
    assert entity.color_temp_kelvin == 2700
    
    mock_coordinator.data = {"temperature": 6000}
    assert entity.color_temp_kelvin == 5000
    
    # Test with no data
    mock_coordinator.data = None
    assert entity.color_temp_kelvin is None


@pytest.mark.asyncio
async def test_light_turn_on_monochrome(mock_coordinator, sample_device_info, mock_mqtt_client):
    """Test turn_on method for monochrome light."""
    entity = HafeleLightEntity(
        mock_coordinator, 123, sample_device_info, mock_mqtt_client, "hafele"
    )
    mock_coordinator.data = {}
    
    # Test turning on with brightness
    await entity.async_turn_on(brightness=128)
    
    # Verify MQTT publish was called for power and lightness
    assert mock_mqtt_client.async_publish.call_count >= 2
    mock_coordinator.hass.async_create_task.assert_called_once()
    
    # Verify optimistic update
    assert mock_coordinator.data.get("onoff") == 1
    assert "lightness" in mock_coordinator.data


@pytest.mark.asyncio
async def test_light_turn_on_multiwhite(mock_coordinator, sample_multiwhite_device_info, mock_mqtt_client):
    """Test turn_on method for multiwhite light."""
    entity = HafeleLightEntity(
        mock_coordinator, 456, sample_multiwhite_device_info, mock_mqtt_client, "hafele"
    )
    mock_coordinator.data = {}
    
    # Test turning on with brightness and color temp
    await entity.async_turn_on(brightness=128, color_temp_kelvin=3500)
    
    # Verify MQTT publish was called for CTL
    mock_mqtt_client.async_publish.assert_called_once()
    call_args = mock_mqtt_client.async_publish.call_args
    assert "ctl" in call_args[0][0]  # Topic contains "ctl"
    
    # Verify optimistic update
    assert mock_coordinator.data.get("onoff") == 1
    assert "lightness" in mock_coordinator.data
    assert "temperature" in mock_coordinator.data


@pytest.mark.asyncio
async def test_light_turn_off(mock_coordinator, sample_device_info, mock_mqtt_client):
    """Test turn_off method."""
    entity = HafeleLightEntity(
        mock_coordinator, 123, sample_device_info, mock_mqtt_client, "hafele"
    )
    mock_coordinator.data = {"onoff": 1}
    
    await entity.async_turn_off()
    
    # Verify MQTT publish was called
    mock_mqtt_client.async_publish.assert_called_once()
    call_args = mock_mqtt_client.async_publish.call_args
    assert "power" in call_args[0][0]  # Topic contains "power"
    
    # Verify optimistic update
    assert mock_coordinator.data.get("onoff") == 0


@pytest.mark.asyncio
async def test_priority_system(mock_coordinator, sample_device_info, mock_mqtt_client):
    """Test polling priority system."""
    entity = HafeleLightEntity(
        mock_coordinator, 123, sample_device_info, mock_mqtt_client, "hafele"
    )
    
    # Initially NORMAL priority
    assert entity.priority == PollPriority.NORMAL
    
    # Set to HIGH priority
    entity.set_high_priority()
    assert entity.priority == PollPriority.HIGH
    
    # Reset to NORMAL
    entity.reset_priority()
    assert entity.priority == PollPriority.NORMAL


@pytest.mark.asyncio
async def test_force_manual_update_normal_mode(mock_coordinator, sample_device_info, mock_mqtt_client):
    """Test force_manual_update in normal polling mode."""
    entity = HafeleLightEntity(
        mock_coordinator, 123, sample_device_info, mock_mqtt_client, "hafele"
    )
    mock_coordinator.polling_mode = POLLING_MODE_NORMAL
    
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await entity.force_manual_update()
    
    # Should publish get request after delay
    assert mock_mqtt_client.async_publish.called
    assert entity.priority == PollPriority.HIGH


@pytest.mark.asyncio
async def test_force_manual_update_rotational_mode(mock_coordinator, sample_device_info, mock_mqtt_client):
    """Test force_manual_update in rotational polling mode."""
    entity = HafeleLightEntity(
        mock_coordinator, 123, sample_device_info, mock_mqtt_client, "hafele"
    )
    mock_coordinator.polling_mode = POLLING_MODE_ROTATIONAL
    
    with patch("asyncio.sleep", new_callable=AsyncMock):
        await entity.force_manual_update()
    
    # Should only set priority, not publish
    assert entity.priority == PollPriority.HIGH


@pytest.mark.asyncio
async def test_coordinator_status_message(mock_hass, mock_mqtt_client):
    """Test coordinator status message handling."""
    coordinator = HafeleLightCoordinator(
        mock_hass,
        mock_mqtt_client,
        123,
        "Test Light",
        "hafele",
        30,
        3,
        POLLING_MODE_NORMAL,
    )
    
    # Simulate status message
    status_data = {"lightness": 0.75, "onoff": 1}
    coordinator._on_status_message("hafele/lights/Test Light/status", status_data)
    
    # Verify data was merged
    assert coordinator._status_data["lightness"] == 0.75
    assert coordinator._status_data["onoff"] == 1


@pytest.mark.asyncio
async def test_coordinator_update_data(mock_hass, mock_mqtt_client):
    """Test coordinator data update."""
    coordinator = HafeleLightCoordinator(
        mock_hass,
        mock_mqtt_client,
        123,
        "Test Light",
        "hafele",
        30,
        3,
        POLLING_MODE_NORMAL,
    )
    
    # Mock entity
    entity = MagicMock()
    entity.is_multiwhite = False
    coordinator.entity = entity
    
    # Mock status response
    coordinator._status_received = True
    coordinator._status_data = {"lightness": 0.5, "onoff": 1}
    
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await coordinator._async_update_data()
    
    # Verify publish was called
    mock_mqtt_client.async_publish.assert_called_once()
    assert result["lightness"] == 0.5


@pytest.mark.asyncio
async def test_coordinator_update_data_timeout(mock_hass, mock_mqtt_client):
    """Test coordinator update timeout handling."""
    coordinator = HafeleLightCoordinator(
        mock_hass,
        mock_mqtt_client,
        123,
        "Test Light",
        "hafele",
        30,
        1,  # Short timeout
        POLLING_MODE_NORMAL,
    )
    
    entity = MagicMock()
    entity.is_multiwhite = False
    coordinator.entity = entity
    coordinator._status_data = {"lightness": 0.3}  # Old data
    
    # No response will come
    coordinator._status_received = False
    
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await coordinator._async_update_data()
    
    # Should return old data on timeout
    assert result == {"lightness": 0.3}
