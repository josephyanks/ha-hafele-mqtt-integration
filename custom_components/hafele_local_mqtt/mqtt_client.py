"""MQTT client wrapper for Hafele Local MQTT."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

try:
    from aiomqtt import Client as MQTTClient
    from aiomqtt.exceptions import MqttError

    AIOMQTT_AVAILABLE = True
except ImportError:
    AIOMQTT_AVAILABLE = False
    _LOGGER.warning("aiomqtt not available, direct MQTT connections disabled")


class HafeleMQTTClient:
    """MQTT client for Hafele Local MQTT devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        topic_prefix: str,
        broker: str | None = None,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize the MQTT client."""
        self.hass = hass
        self.topic_prefix = topic_prefix
        self._subscriptions: dict[str, Callable] = {}
        self._use_ha_mqtt = broker is None
        self._broker = broker
        self._port = port
        self._username = username
        self._password = password
        self._mqtt_client: MQTTClient | None = None
        self._connected = False
        self._message_listener_task: asyncio.Task | None = None
        self._unsubscribers: dict[str, Callable[[], None]] = {}

    async def async_connect(self) -> None:
        """Connect to MQTT broker."""
        if self._use_ha_mqtt:
            # Use Home Assistant's MQTT integration
            if not mqtt.is_connected(self.hass):
                _LOGGER.error("MQTT broker is not connected")
                raise ConnectionError("MQTT broker is not connected")
            _LOGGER.info("MQTT client connected via Home Assistant MQTT")
        else:
            # Use direct MQTT connection
            if not AIOMQTT_AVAILABLE:
                raise ImportError(
                    "aiomqtt is required for direct MQTT connections. "
                    "Install it with: pip install aiomqtt"
                )

            try:
                self._mqtt_client = MQTTClient(
                    hostname=self._broker,
                    port=self._port,
                    username=self._username,
                    password=self._password,
                )
                await self._mqtt_client.__aenter__()
                self._connected = True
                
                # Start message listener task
                self._message_listener_task = asyncio.create_task(self._message_listener())
                
                _LOGGER.info(
                    "MQTT client connected directly to %s:%s", self._broker, self._port
                )
            except MqttError as err:
                _LOGGER.error("Failed to connect to MQTT broker: %s", err)
                raise ConnectionError(f"Failed to connect to MQTT broker: {err}") from err

    async def async_disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        # Unsubscribe from all topics
        for topic in list(self._subscriptions.keys()):
            await self.async_unsubscribe(topic)

        if not self._use_ha_mqtt:
            # Cancel message listener task
            if self._message_listener_task:
                self._message_listener_task.cancel()
                try:
                    await self._message_listener_task
                except asyncio.CancelledError:
                    pass
                self._message_listener_task = None

            if self._mqtt_client:
                try:
                    await self._mqtt_client.__aexit__(None, None, None)
                    self._connected = False
                except Exception as err:
                    _LOGGER.error("Error disconnecting from MQTT broker: %s", err)

        _LOGGER.info("MQTT client disconnected")

    async def async_subscribe(
        self, topic: str, callback: Callable[[str, Any], None], qos: int = 0
    ) -> Callable[[], None]:
        """Subscribe to an MQTT topic."""
        _LOGGER.debug("Subscribing to topic: %s", topic)

        if self._use_ha_mqtt:
            # Use Home Assistant's MQTT integration
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
        else:
            # Use direct MQTT connection
            if not self._mqtt_client or not self._connected:
                raise ConnectionError("MQTT client not connected")

            await self._mqtt_client.subscribe(topic, qos=qos)
            self._subscriptions[topic] = callback

            # Return unsubscribe function
            async def unsubscribe():
                if topic in self._subscriptions:
                    await self._mqtt_client.unsubscribe(topic)
                    del self._subscriptions[topic]

            self._unsubscribers[topic] = unsubscribe
            return unsubscribe

    async def async_unsubscribe(self, topic: str) -> None:
        """Unsubscribe from an MQTT topic."""
        if topic in self._unsubscribers:
            await self._unsubscribers[topic]()
            del self._unsubscribers[topic]
        elif topic in self._subscriptions:
            # For HA MQTT, the unsubscribe is handled by the returned function
            del self._subscriptions[topic]
            _LOGGER.debug("Unsubscribed from topic: %s", topic)

    async def async_publish(
        self, topic: str, payload: str | dict[str, Any] | bool, qos: int = 0, retain: bool = False
    ) -> None:
        """Publish a message to an MQTT topic."""
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        elif isinstance(payload, bool):
            # Convert boolean to JSON string (true/false)
            payload = json.dumps(payload)

        _LOGGER.debug("Publishing to topic %s: %s", topic, payload)

        if self._use_ha_mqtt:
            await mqtt.async_publish(self.hass, topic, payload, qos=qos, retain=retain)
        else:
            if not self._mqtt_client or not self._connected:
                raise ConnectionError("MQTT client not connected")
            await self._mqtt_client.publish(topic, payload.encode(), qos=qos, retain=retain)
    
    async def _message_listener(self) -> None:
        """Background task to listen for MQTT messages."""
        if not self._mqtt_client:
            return
        
        try:
            async for msg in self._mqtt_client.messages:
                topic = msg.topic.value
                if topic in self._subscriptions:
                    callback = self._subscriptions[topic]
                    try:
                        payload = msg.payload
                        # Try to parse as JSON, fallback to string
                        try:
                            data = json.loads(payload)
                        except (json.JSONDecodeError, TypeError):
                            data = payload.decode("utf-8") if isinstance(payload, bytes) else payload
                        
                        # Call the callback directly (it's synchronous)
                        # We're already in the HA event loop, so this is safe
                        callback(topic, data)
                    except Exception as err:
                        _LOGGER.error("Error processing MQTT message on %s: %s", topic, err)
        except asyncio.CancelledError:
            _LOGGER.debug("Message listener task cancelled")
        except Exception as err:
            _LOGGER.error("Error in message listener: %s", err)

