"""Config flow for Hafele Local MQTT integration."""
from __future__ import annotations

import asyncio
import logging
import secrets
import socket
import string
from typing import Any
import uuid

import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ENABLE_GROUPS,
    CONF_ENABLE_SCENES,
    CONF_MQTT_BROKER,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_POLLING_INTERVAL,
    CONF_POLLING_MODE,
    CONF_POLLING_TIMEOUT,
    CONF_TOPIC_PREFIX,
    CONF_USE_HA_MQTT,
    DEFAULT_MQTT_PORT,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_POLLING_MODE,
    DEFAULT_POLLING_TIMEOUT,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    POLLING_MODE_NORMAL,
    POLLING_MODE_ROTATIONAL,
)

_LOGGER = logging.getLogger(__name__)


def generate_password(length: int = 12) -> str:
    """Generate a secure, random alphanumeric and special character password.

    Args:
        length: The character length of the generated password string.

    Returns:
        A cryptographically secure random password.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%&*-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def validate_manual_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate manual MQTT broker configuration by performing a test connection.

    Args:
        hass: The HomeAssistant instance core wrapper.
        data: User configuration data containing broker URL, port, and credentials.

    Returns:
        A dictionary containing the user-facing title for the integration entry.

    Raises:
        CannotConnect: If connection to the broker fails or times out.
    """
    try:
        import paho.mqtt.client as mqtt_client

        client = mqtt_client.Client()

        if data.get(CONF_MQTT_USERNAME) and data.get(CONF_MQTT_PASSWORD):
            client.username_pw_set(data[CONF_MQTT_USERNAME], data[CONF_MQTT_PASSWORD])

        # Run blocking connection test in the Home Assistant executor thread pool
        await hass.async_add_executor_job(
            client.connect, data[CONF_MQTT_BROKER], data[CONF_MQTT_PORT], 10
        )
        await hass.async_add_executor_job(client.disconnect)

        return {"title": f"Häfele Mesh ({data[CONF_MQTT_BROKER]})"}
    except Exception as err:
        _LOGGER.error("Could not connect to MQTT broker: %s", err)
        raise CannotConnect from err


async def create_mosquitto_user(
    hass: HomeAssistant, base_username: str, password: str
) -> tuple[bool, str]:
    """Create a localized Home Assistant user account and restart the Mosquitto Add-on.

    This enables automated provisioning for standard Home Assistant OS/Supervised setups
    running the official Mosquitto MQTT Broker addon.

    Args:
        hass: The HomeAssistant instance core wrapper.
        base_username: The starting prefix for the generated username.
        password: The security password token generated for this user.

    Returns:
        A tuple of (success_status, final_generated_username).
    """
    random_code = uuid.uuid4().hex[:6]
    actual_username = f"{base_username}_{random_code}"

    try:
        # Fetch the default homeassistant authentication provider
        provider = next(
            (prv for prv in hass.auth.auth_providers if prv.type == "homeassistant"), None
        )
        if not provider:
            return False, ""

        await provider.async_initialize()
        await provider.async_add_auth(actual_username, password)

        # Create user profile within Home Assistant UI
        display_name = f"MQTT Client ({actual_username})"
        user = await hass.auth.async_create_user(display_name, group_ids=[GROUP_ID_USER])

        # Link auth provider credentials to the newly minted user
        credentials = await provider.async_get_or_create_credentials(
            {"username": actual_username}
        )
        await hass.auth.async_link_user(user, credentials)
        await asyncio.sleep(3)

        # Safely attempt to restart the local supervisor Mosquitto service
        try:
            await hass.services.async_call(
                domain="hassio",
                service="addon_restart",
                service_data={"addon": "core_mosquitto"},
                blocking=True,
            )
            await asyncio.sleep(10)  # Yield block to let broker initialize
        except Exception:
            _LOGGER.warning(
                "Could not automatically restart Mosquitto add-on. "
                "User might be running container/core installations."
            )

        return True, actual_username
    except Exception:
        _LOGGER.exception("Failed to dynamically configure a new Mosquitto user profile")
        return False, ""


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a configuration setup flow for the Häfele Mesh local MQTT integration."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow layout data variables."""
        self._mqtt_config: dict[str, Any] = {}
        self._generated_username: str | None = None
        self._generated_password: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 1: Present options to choose between an Automatic or Manual configuration path.

        Args:
            user_input: User selection option from the initial frontend form.
        """
        if user_input is not None:
            if user_input["setup_type"] == "automatic":
                return await self.async_step_automatic()
            return await self.async_step_manual()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("setup_type", default="automatic"): vol.In(
                        {"automatic": "automatic", "manual": "manual"}
                    )
                }
            ),
        )

    async def async_step_automatic(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2a: Execute automatic Mosquitto credentials creation and configuration provisioning.

        Args:
            user_input: Integration parameters configuration form values.
        """
        if user_input is not None:
            username = "haefele_mesh"
            password = generate_password()

            user_created, actual_username = await create_mosquitto_user(
                self.hass, username, password
            )

            # Fall back safely to manual setup options if automated provisioning fails
            if not user_created:
                return await self.async_step_manual()

            self._mqtt_config = {
                CONF_MQTT_BROKER: "localhost",
                CONF_MQTT_PORT: 1883,
                CONF_MQTT_USERNAME: actual_username,
                CONF_MQTT_PASSWORD: password,
                CONF_TOPIC_PREFIX: user_input.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
                CONF_USE_HA_MQTT: False,
                CONF_POLLING_INTERVAL: DEFAULT_POLLING_INTERVAL,
                CONF_POLLING_MODE: DEFAULT_POLLING_MODE,
                CONF_ENABLE_GROUPS: True,
                CONF_ENABLE_SCENES: True,
            }
            self._generated_username = actual_username
            self._generated_password = password

            return await self.async_step_show_credentials()

        return self.async_show_form(
            step_id="automatic",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOPIC_PREFIX, default=DEFAULT_TOPIC_PREFIX): str,
                }
            ),
        )

    async def async_step_show_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Render generated credentials to user and validate connectivity on final submission.

        Args:
            user_input: Confirmation submission data from frontend form.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Test connectivity using the manual pipeline logic
                await validate_manual_input(self.hass, self._mqtt_config)

                await self.async_set_unique_id(
                    f"auto_{self._mqtt_config[CONF_TOPIC_PREFIX]}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Häfele Mesh (Auto)", data=self._mqtt_config
                )
            except CannotConnect:
                # Occurs if Mosquitto takes longer than expected to cycle restart
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"

        # Dynamically discover local private IP address to display setup configuration hints
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "YOUR_HA_IP"

        return self.async_show_form(
            step_id="show_credentials",
            description_placeholders={
                "broker_url": f"mqtt://{local_ip}:1883",
                "username": self._generated_username,
                "password": self._generated_password,
                "topic": self._mqtt_config[CONF_TOPIC_PREFIX],
            },
            errors=errors,
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 2b: Display form elements to capture custom, self-managed MQTT configuration properties.

        Args:
            user_input: Dictionary bundle of manual inputs typed in by user.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_manual_input(self.hass, user_input)

                await self.async_set_unique_id(
                    f"{user_input[CONF_MQTT_BROKER]}_{user_input[CONF_TOPIC_PREFIX]}"
                )
                self._abort_if_unique_id_configured()

                entry_data = {**user_input, CONF_USE_HA_MQTT: False}
                return self.async_create_entry(title=info["title"], data=entry_data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MQTT_BROKER, default="localhost"): str,
                    vol.Required(CONF_MQTT_PORT, default=1883): cv.port,
                    vol.Optional(CONF_MQTT_USERNAME): str,
                    vol.Optional(CONF_MQTT_PASSWORD): str,
                    vol.Required(CONF_TOPIC_PREFIX, default=DEFAULT_TOPIC_PREFIX): str,
                    vol.Optional(
                        CONF_POLLING_INTERVAL, default=DEFAULT_POLLING_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=2)),
                    vol.Optional(
                        CONF_POLLING_TIMEOUT, default=DEFAULT_POLLING_TIMEOUT
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
                    vol.Optional(CONF_POLLING_MODE, default=POLLING_MODE_NORMAL): vol.In(
                        [POLLING_MODE_NORMAL, POLLING_MODE_ROTATIONAL]
                    ),
                    vol.Optional(CONF_ENABLE_GROUPS, default=True): bool,
                    vol.Optional(CONF_ENABLE_SCENES, default=True): bool,
                }
            ),
            errors=errors,
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Exception raised when unable to establish communication with the target MQTT Broker."""
