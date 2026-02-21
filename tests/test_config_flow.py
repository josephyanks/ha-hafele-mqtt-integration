"""Tests for Hafele config flow."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hafele_local_mqtt.config_flow import HafeleConfigFlow
from custom_components.hafele_local_mqtt.const import DOMAIN


@pytest.fixture
def flow():
    """Create config flow."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.flow = MagicMock()
    flow = HafeleConfigFlow()
    flow.hass = hass
    return flow


@pytest.mark.asyncio
async def test_config_flow_user_step_no_input(flow):
    """Test config flow user step with no input."""
    result = await flow.async_step_user()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


@pytest.mark.asyncio
@patch("custom_components.hafele_local_mqtt.config_flow.mqtt")
async def test_config_flow_user_step_ha_mqtt(mock_mqtt, flow):
    """Test config flow with HA MQTT."""
    mock_mqtt.is_connected.return_value = True
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    
    user_input = {
        "use_ha_mqtt": True,
        "topic_prefix": "hafele",
        "polling_interval": 30,
        "polling_timeout": 3,
        "polling_mode": "normal",
    }
    
    result = await flow.async_step_user(user_input)
    
    assert result["type"] == "create_entry"


@pytest.mark.asyncio
@patch("custom_components.hafele_local_mqtt.config_flow.mqtt")
async def test_config_flow_user_step_ha_mqtt_not_connected(mock_mqtt, flow):
    """Test config flow with HA MQTT not connected."""
    mock_mqtt.is_connected.return_value = False
    
    user_input = {
        "use_ha_mqtt": True,
        "topic_prefix": "hafele",
    }
    
    result = await flow.async_step_user(user_input)
    
    assert result["type"] == FlowResultType.FORM
    assert "errors" in result
    assert result["errors"]["base"] == "ha_mqtt_not_connected"


@pytest.mark.asyncio
async def test_config_flow_user_step_direct_mqtt_no_broker(flow):
    """Test config flow with direct MQTT but no broker."""
    user_input = {
        "use_ha_mqtt": False,
        "topic_prefix": "hafele",
    }
    
    result = await flow.async_step_user(user_input)
    
    assert result["type"] == FlowResultType.FORM
    assert "errors" in result
    assert result["errors"]["base"] == "mqtt_broker_required"
