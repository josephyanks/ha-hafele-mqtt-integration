"""Tests for Hafele button platform."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.hafele_local_mqtt.button import HafelePingButton
from custom_components.hafele_local_mqtt.const import (
    TOPIC_GET_DEVICE_LIGHTNESS,
    TOPIC_GET_DEVICE_POWER,
    TOPIC_GET_DEVICE_CTL,
)


@pytest.mark.asyncio
async def test_button_press_lightness_monochrome(mock_mqtt_client):
    """Test lightness button press for monochrome device."""
    device_info = {
        "device_name": "Test Light",
        "device_addr": 123,
        "device_types": ["Light"],
    }
    
    button = HafelePingButton(
        mock_mqtt_client,
        123,
        device_info,
        "Test Light",
        "hafele",
        "lightness",
        "Ping lightness",
        "123_ping_lightness",
    )
    
    await button.async_press()
    
    # Verify publish was called
    mock_mqtt_client.async_publish.assert_called_once()
    call_args = mock_mqtt_client.async_publish.call_args
    assert TOPIC_GET_DEVICE_LIGHTNESS.format(
        prefix="hafele", device_name="Test Light"
    ) in call_args[0][0] or "lightnessGet" in call_args[0][0]


@pytest.mark.asyncio
async def test_button_press_lightness_multiwhite(mock_mqtt_client):
    """Test lightness button press for multiwhite device."""
    device_info = {
        "device_name": "Test Multiwhite",
        "device_addr": 456,
        "device_types": ["Multiwhite"],
    }
    
    button = HafelePingButton(
        mock_mqtt_client,
        456,
        device_info,
        "Test Multiwhite",
        "hafele",
        "lightness",
        "Ping lightness",
        "456_ping_lightness",
    )
    
    await button.async_press()
    
    # Verify CTL topic was used for multiwhite
    mock_mqtt_client.async_publish.assert_called_once()
    call_args = mock_mqtt_client.async_publish.call_args
    assert "ctl" in call_args[0][0].lower()


@pytest.mark.asyncio
async def test_button_press_power(mock_mqtt_client):
    """Test power button press."""
    device_info = {
        "device_name": "Test Light",
        "device_addr": 123,
        "device_types": ["Light"],
    }
    
    button = HafelePingButton(
        mock_mqtt_client,
        123,
        device_info,
        "Test Light",
        "hafele",
        "power",
        "Ping power",
        "123_ping_power",
    )
    
    await button.async_press()
    
    mock_mqtt_client.async_publish.assert_called_once()
    call_args = mock_mqtt_client.async_publish.call_args
    assert "power" in call_args[0][0].lower()
