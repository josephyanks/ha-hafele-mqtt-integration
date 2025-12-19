"""MQTT client wrapper for Hafele Local MQTT."""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HafeleMQTTClient:
    """MQTT client for Hafele Local MQTT devices."""

    def __init__(self, hass: HomeAssistant, topic_prefix: str) -> None:
        """Initialize the MQTT client."""
        self.hass = hass
        self.topic_prefix = topic_prefix
        self._subscriptions: dict[str, Callable] = {}

    async def async_connect(self) -> None:
        """Connect to MQTT broker."""
        # MQTT integration should already be set up in Home Assistant
        # We just need to verify it's available
        if not mqtt.is_connected(self.hass):
            _LOGGER.error("MQTT broker is not connected")
            raise ConnectionError("MQTT broker is not connected")

        _LOGGER.info("MQTT client connected")

    async def async_disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        # Unsubscribe from all topics
        for topic in list(self._subscriptions.keys()):
            await self.async_unsubscribe(topic)
        _LOGGER.info("MQTT client disconnected")

    async def async_subscribe(
        self, topic: str, callback: Callable[[str, Any], None], qos: int = 0
    ) -> Callable[[], None]:
        """Subscribe to an MQTT topic."""
        _LOGGER.debug("Subscribing to topic: %s", topic)

        async def message_received(msg: mqtt.ReceiveMessage) -> None:
            """Handle received MQTT message."""
            try:
                payload = msg.payload
                # Try to parse as JSON, fallback to string
                try:
                    data = json.loads(payload)
                except (json.JSONDecodeError, TypeError):
                    data = payload.decode("utf-8") if isinstance(payload, bytes) else payload

                callback(topic, data)
            except Exception as err:
                _LOGGER.error("Error processing MQTT message on %s: %s", topic, err)

        unsubscribe = await mqtt.async_subscribe(
            self.hass, topic, message_received, qos=qos
        )
        self._subscriptions[topic] = callback

        return unsubscribe

    async def async_unsubscribe(self, topic: str) -> None:
        """Unsubscribe from an MQTT topic."""
        if topic in self._subscriptions:
            # The unsubscribe callback would be stored if we needed it
            # For now, mqtt.async_unsubscribe handles it
            del self._subscriptions[topic]
            _LOGGER.debug("Unsubscribed from topic: %s", topic)

    async def async_publish(
        self, topic: str, payload: str | dict[str, Any], qos: int = 0, retain: bool = False
    ) -> None:
        """Publish a message to an MQTT topic."""
        if isinstance(payload, dict):
            payload = json.dumps(payload)

        _LOGGER.debug("Publishing to topic %s: %s", topic, payload)
        await mqtt.async_publish(self.hass, topic, payload, qos=qos, retain=retain)

