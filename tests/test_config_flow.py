"""Tests for Hafele config flow (automatic + manual setup)."""
from __future__ import annotations

import sys
import types

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.data_entry_flow import FlowResultType

from custom_components.hafele_local_mqtt.config_flow import (
    CannotConnect,
    ConfigFlow,
    create_mosquitto_user,
    generate_password,
    validate_manual_input,
)
from custom_components.hafele_local_mqtt.const import (
    CONF_ENABLE_GROUPS,
    CONF_ENABLE_SCENES,
    CONF_MQTT_BROKER,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_POLLING_INTERVAL,
    CONF_POLLING_MODE,
    CONF_TOPIC_PREFIX,
    CONF_USE_HA_MQTT,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_POLLING_MODE,
    POLLING_MODE_NORMAL,
)


@pytest.fixture
def flow():
    """Create config flow with mocked hass."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
    hass.auth = MagicMock()
    hass.auth.auth_providers = []
    hass.auth.async_create_user = AsyncMock()
    hass.auth.async_link_user = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    config_flow = ConfigFlow()
    config_flow.hass = hass
    config_flow.async_set_unique_id = AsyncMock()
    config_flow._abort_if_unique_id_configured = MagicMock()
    return config_flow


def test_generate_password_length_and_charset():
    """Generated passwords meet length and character set requirements."""
    password = generate_password(16)
    assert len(password) == 16
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%&*-_")
    assert all(c in allowed for c in password)


@pytest.mark.asyncio
async def test_validate_manual_input_success():
    """Successful broker connection returns a display title."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))

    mock_client = MagicMock()
    paho_client_mod = types.ModuleType("paho.mqtt.client")
    paho_client_mod.Client = MagicMock(return_value=mock_client)
    paho_mqtt_mod = types.ModuleType("paho.mqtt")
    paho_mqtt_mod.client = paho_client_mod
    paho_mod = types.ModuleType("paho")
    paho_mod.mqtt = paho_mqtt_mod

    with patch.dict(
        sys.modules,
        {
            "paho": paho_mod,
            "paho.mqtt": paho_mqtt_mod,
            "paho.mqtt.client": paho_client_mod,
        },
    ):
        result = await validate_manual_input(
            hass,
            {
                CONF_MQTT_BROKER: "192.168.1.10",
                CONF_MQTT_PORT: 1883,
                CONF_MQTT_USERNAME: "user",
                CONF_MQTT_PASSWORD: "pass",
            },
        )

    assert result["title"] == "Häfele Mesh (192.168.1.10)"
    mock_client.username_pw_set.assert_called_once_with("user", "pass")
    assert hass.async_add_executor_job.await_count == 2


@pytest.mark.asyncio
async def test_validate_manual_input_raises_cannot_connect():
    """Broker connection failure raises CannotConnect."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=RuntimeError("connection refused"))

    with pytest.raises(CannotConnect):
        await validate_manual_input(
            hass, {CONF_MQTT_BROKER: "bad.host", CONF_MQTT_PORT: 1883}
        )


@pytest.mark.asyncio
async def test_create_mosquitto_user_success(flow):
    """Provisioning creates auth, user, and restarts Mosquitto addon."""
    provider = MagicMock()
    provider.type = "homeassistant"
    provider.async_initialize = AsyncMock()
    provider.async_add_auth = AsyncMock()
    provider.async_get_or_create_credentials = AsyncMock(return_value=MagicMock())
    flow.hass.auth.auth_providers = [provider]

    with patch(
        "custom_components.hafele_local_mqtt.config_flow.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        ok, username = await create_mosquitto_user(flow.hass, "haefele_mesh", "secret-pass")

    assert ok is True
    assert username.startswith("haefele_mesh_")
    provider.async_add_auth.assert_awaited_once()
    flow.hass.auth.async_create_user.assert_awaited_once()
    flow.hass.services.async_call.assert_awaited_once_with(
        domain="hassio",
        service="addon_restart",
        service_data={"addon": "core_mosquitto"},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_create_mosquitto_user_no_provider(flow):
    """Returns failure when homeassistant auth provider is missing."""
    flow.hass.auth.auth_providers = []
    ok, username = await create_mosquitto_user(flow.hass, "haefele_mesh", "secret-pass")
    assert ok is False
    assert username == ""


@pytest.mark.asyncio
async def test_config_flow_user_step_no_input(flow):
    """Initial step shows automatic vs manual choice."""
    result = await flow.async_step_user()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_config_flow_user_step_routes_to_manual(flow):
    """Choosing manual setup opens the manual configuration form."""
    result = await flow.async_step_user({"setup_type": "manual"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"


@pytest.mark.asyncio
async def test_config_flow_user_step_routes_to_automatic(flow):
    """Choosing automatic setup opens the automatic configuration form."""
    result = await flow.async_step_user({"setup_type": "automatic"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "automatic"


@pytest.mark.asyncio
@patch(
    "custom_components.hafele_local_mqtt.config_flow.validate_manual_input",
    new_callable=AsyncMock,
)
async def test_config_flow_manual_success(mock_validate, flow):
    """Manual setup creates an entry after broker validation."""
    mock_validate.return_value = {"title": "Häfele Mesh (localhost)"}
    user_input = {
        CONF_MQTT_BROKER: "localhost",
        CONF_MQTT_PORT: 1883,
        CONF_TOPIC_PREFIX: "Mesh",
        CONF_ENABLE_GROUPS: True,
        CONF_ENABLE_SCENES: True,
    }

    result = await flow.async_step_manual(user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Häfele Mesh (localhost)"
    assert result["data"][CONF_USE_HA_MQTT] is False
    flow.async_set_unique_id.assert_awaited_with("localhost_Mesh")


@pytest.mark.asyncio
@patch(
    "custom_components.hafele_local_mqtt.config_flow.validate_manual_input",
    new_callable=AsyncMock,
)
async def test_config_flow_manual_cannot_connect(mock_validate, flow):
    """Manual setup surfaces cannot_connect when broker validation fails."""
    mock_validate.side_effect = CannotConnect()
    user_input = {
        CONF_MQTT_BROKER: "localhost",
        CONF_MQTT_PORT: 1883,
        CONF_TOPIC_PREFIX: "Mesh",
    }

    result = await flow.async_step_manual(user_input)

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.asyncio
@patch(
    "custom_components.hafele_local_mqtt.config_flow.create_mosquitto_user",
    new_callable=AsyncMock,
)
async def test_config_flow_automatic_falls_back_to_manual(mock_create_user, flow):
    """Automatic setup falls back to manual when user provisioning fails."""
    mock_create_user.return_value = (False, "")
    result = await flow.async_step_automatic({CONF_TOPIC_PREFIX: "Mesh"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"


@pytest.mark.asyncio
@patch(
    "custom_components.hafele_local_mqtt.config_flow.create_mosquitto_user",
    new_callable=AsyncMock,
)
async def test_config_flow_automatic_shows_credentials(mock_create_user, flow):
    """Successful automatic provisioning advances to credentials step."""
    mock_create_user.return_value = (True, "haefele_mesh_abc123")
    result = await flow.async_step_automatic({CONF_TOPIC_PREFIX: "Mesh"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "show_credentials"
    assert flow._generated_username == "haefele_mesh_abc123"
    assert flow._mqtt_config[CONF_MQTT_BROKER] == "localhost"
    assert flow._mqtt_config[CONF_USE_HA_MQTT] is False


@pytest.mark.asyncio
@patch(
    "custom_components.hafele_local_mqtt.config_flow.validate_manual_input",
    new_callable=AsyncMock,
)
async def test_config_flow_show_credentials_creates_entry(mock_validate, flow):
    """Credentials confirmation creates auto-configured integration entry."""
    flow._mqtt_config = {
        CONF_MQTT_BROKER: "localhost",
        CONF_MQTT_PORT: 1883,
        CONF_MQTT_USERNAME: "haefele_mesh_abc123",
        CONF_MQTT_PASSWORD: "generated",
        CONF_TOPIC_PREFIX: "Mesh",
        CONF_USE_HA_MQTT: False,
    }
    flow._generated_username = "haefele_mesh_abc123"
    flow._generated_password = "generated"

    result = await flow.async_step_show_credentials({})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Häfele Mesh (Auto)"
    assert result["data"][CONF_USE_HA_MQTT] is False
    flow.async_set_unique_id.assert_awaited_with("auto_Mesh")


@pytest.mark.asyncio
async def test_create_mosquitto_user_succeeds_when_addon_restart_fails(flow):
    """Provisioning still succeeds when Hass.io Mosquitto restart is unavailable."""
    provider = MagicMock()
    provider.type = "homeassistant"
    provider.async_initialize = AsyncMock()
    provider.async_add_auth = AsyncMock()
    provider.async_get_or_create_credentials = AsyncMock(return_value=MagicMock())
    flow.hass.auth.auth_providers = [provider]
    flow.hass.services.async_call = AsyncMock(side_effect=RuntimeError("no hassio"))

    with patch(
        "custom_components.hafele_local_mqtt.config_flow.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        ok, username = await create_mosquitto_user(flow.hass, "haefele_mesh", "secret-pass")

    assert ok is True
    assert username.startswith("haefele_mesh_")


@pytest.mark.asyncio
async def test_config_flow_show_credentials_displays_local_ip(flow):
    """Credentials step shows broker URL using discovered local IP."""
    flow._mqtt_config = {CONF_TOPIC_PREFIX: "Mesh"}
    flow._generated_username = "haefele_mesh_abc123"
    flow._generated_password = "generated"

    mock_sock = MagicMock()
    mock_sock.getsockname.return_value = ("192.168.50.42", 54321)

    with patch(
        "custom_components.hafele_local_mqtt.config_flow.socket.socket",
        return_value=mock_sock,
    ):
        result = await flow.async_step_show_credentials()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "show_credentials"
    placeholders = result["description_placeholders"]
    assert placeholders["broker_url"] == "mqtt://192.168.50.42:1883"
    assert placeholders["username"] == "haefele_mesh_abc123"
    assert placeholders["password"] == "generated"
    assert placeholders["topic"] == "Mesh"
    mock_sock.connect.assert_called_once_with(("8.8.8.8", 80))
    mock_sock.close.assert_called_once()


@pytest.mark.asyncio
async def test_config_flow_show_credentials_fallback_ip_on_socket_error(flow):
    """Credentials step falls back when local IP discovery fails."""
    flow._mqtt_config = {CONF_TOPIC_PREFIX: "Mesh"}
    flow._generated_username = "haefele_mesh_abc123"
    flow._generated_password = "generated"

    with patch(
        "custom_components.hafele_local_mqtt.config_flow.socket.socket",
        side_effect=OSError("network unreachable"),
    ):
        result = await flow.async_step_show_credentials()

    assert result["description_placeholders"]["broker_url"] == "mqtt://YOUR_HA_IP:1883"


@pytest.mark.asyncio
@patch(
    "custom_components.hafele_local_mqtt.config_flow.validate_manual_input",
    new_callable=AsyncMock,
)
async def test_config_flow_show_credentials_cannot_connect(mock_validate, flow):
    """Credentials confirmation surfaces cannot_connect when broker is not ready."""
    mock_validate.side_effect = CannotConnect()
    flow._mqtt_config = {
        CONF_MQTT_BROKER: "localhost",
        CONF_MQTT_PORT: 1883,
        CONF_MQTT_USERNAME: "haefele_mesh_abc123",
        CONF_MQTT_PASSWORD: "generated",
        CONF_TOPIC_PREFIX: "Mesh",
    }
    flow._generated_username = "haefele_mesh_abc123"
    flow._generated_password = "generated"

    result = await flow.async_step_show_credentials({})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "show_credentials"
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.asyncio
@patch(
    "custom_components.hafele_local_mqtt.config_flow.validate_manual_input",
    new_callable=AsyncMock,
)
@patch(
    "custom_components.hafele_local_mqtt.config_flow.create_mosquitto_user",
    new_callable=AsyncMock,
)
@patch(
    "custom_components.hafele_local_mqtt.config_flow.generate_password",
    return_value="fixed-test-password",
)
async def test_config_flow_automatic_end_to_end(
    mock_password, mock_create_user, mock_validate, flow
):
    """Full automatic path: user -> topic -> credentials -> validated entry."""
    mock_create_user.return_value = (True, "haefele_mesh_e2e01")
    mock_validate.return_value = {"title": "unused"}

    step_user = await flow.async_step_user({"setup_type": "automatic"})
    assert step_user["step_id"] == "automatic"

    step_automatic = await flow.async_step_automatic({CONF_TOPIC_PREFIX: "Kitchen"})
    assert step_automatic["step_id"] == "show_credentials"
    assert flow._mqtt_config == {
        CONF_MQTT_BROKER: "localhost",
        CONF_MQTT_PORT: 1883,
        CONF_MQTT_USERNAME: "haefele_mesh_e2e01",
        CONF_MQTT_PASSWORD: "fixed-test-password",
        CONF_TOPIC_PREFIX: "Kitchen",
        CONF_USE_HA_MQTT: False,
        CONF_POLLING_INTERVAL: DEFAULT_POLLING_INTERVAL,
        CONF_POLLING_MODE: POLLING_MODE_NORMAL,
        CONF_ENABLE_GROUPS: True,
        CONF_ENABLE_SCENES: True,
    }

    step_credentials = await flow.async_step_show_credentials({})
    assert step_credentials["type"] == FlowResultType.CREATE_ENTRY
    assert step_credentials["title"] == "Häfele Mesh (Auto)"
    assert step_credentials["data"][CONF_MQTT_PASSWORD] == "fixed-test-password"
    assert step_credentials["data"][CONF_TOPIC_PREFIX] == "Kitchen"
    assert step_credentials["data"][CONF_USE_HA_MQTT] is False
    flow.async_set_unique_id.assert_awaited_with("auto_Kitchen")
    mock_create_user.assert_awaited_once_with(flow.hass, "haefele_mesh", "fixed-test-password")
    mock_validate.assert_awaited_once_with(flow.hass, flow._mqtt_config)
