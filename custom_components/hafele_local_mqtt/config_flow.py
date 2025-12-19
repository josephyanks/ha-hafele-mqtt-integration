"""Config flow for Hafele Local MQTT integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ENABLE_GROUPS,
    CONF_ENABLE_SCENES,
    CONF_POLLING_INTERVAL,
    CONF_POLLING_TIMEOUT,
    CONF_TOPIC_PREFIX,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_POLLING_TIMEOUT,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_TOPIC_PREFIX, default=DEFAULT_TOPIC_PREFIX): str,
        vol.Optional(
            CONF_POLLING_INTERVAL, default=DEFAULT_POLLING_INTERVAL
        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
        vol.Optional(
            CONF_POLLING_TIMEOUT, default=DEFAULT_POLLING_TIMEOUT
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
        vol.Optional(CONF_ENABLE_GROUPS, default=True): bool,
        vol.Optional(CONF_ENABLE_SCENES, default=True): bool,
    }
)


class HafeleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hafele Local MQTT."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        # Check if already configured
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="Hafele Local MQTT",
            data=user_input,
        )

