# Root conftest: install Home Assistant mocks BEFORE any test code runs.
# Must run before tests/conftest.py is loaded (which imports our package).
import sys
from unittest.mock import Mock

if "homeassistant" not in sys.modules:
    mock_ha = Mock()
    mock_ha.core = Mock()
    mock_ha.core.HomeAssistant = type("HomeAssistant", (), {})
    mock_ha.core.callback = lambda x: x
    mock_ha.config_entries = Mock()
    mock_ha.config_entries.ConfigEntry = type("ConfigEntry", (), {})
    mock_ha.config_entries.Platform = Mock()
    # ConfigFlow base: accepts domain= in subclass and provides flow helpers
    class _ConfigFlow:
        def __init__(self):
            pass
        @classmethod
        def __init_subclass__(cls, domain=None, **kwargs):
            pass
        def async_show_form(self, step_id, data_schema=None, errors=None):
            return {"type": "form", "step_id": step_id, "errors": errors or {}}
        def async_create_entry(self, title, data):
            return {"type": "create_entry", "title": title, "data": data}
        async def async_set_unique_id(self, unique_id):
            pass
        def _abort_if_unique_id_configured(self):
            pass
    mock_ha.config_entries.ConfigFlow = _ConfigFlow

    mock_ha.const = Mock()
    mock_ha.const.Platform = Mock()
    mock_ha.const.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
    mock_ha.components = Mock()
    mock_ha.components.light = Mock()
    mock_ha.components.light.ColorMode = Mock()
    _LightEntityBase = type("LightEntity", (), {"async_write_ha_state": Mock()})
    mock_ha.components.light.LightEntity = _LightEntityBase
    mock_ha.components.light.ATTR_BRIGHTNESS = "brightness"
    mock_ha.components.light.ATTR_COLOR_TEMP_KELVIN = "color_temp_kelvin"
    mock_ha.components.light.COLOR_MODE_COLOR_TEMP = "color_temp"
    mock_ha.components.button = Mock()
    mock_ha.components.button.ButtonEntity = type("ButtonEntity", (), {})
    mock_ha.components.mqtt = Mock()
    mock_ha.components.mqtt.is_connected = Mock(return_value=True)
    mock_ha.components.mqtt.async_subscribe = Mock()
    mock_ha.components.mqtt.async_publish = Mock()
    mock_ha.components.mqtt.ReceiveMessage = Mock()
    mock_ha.helpers = Mock()
    mock_ha.helpers.entity_registry = Mock()
    mock_ha.helpers.entity_registry.EntityRegistry = type("EntityRegistry", (), {})
    mock_ha.helpers.entity_registry.async_get = Mock()
    mock_ha.helpers.device_registry = Mock()
    # Base classes must accept constructor args (coordinator, or hass/logger/name/update_interval)
    class _CoordinatorEntity:
        def __init__(self, coordinator=None, *args, **kwargs):
            self.coordinator = coordinator

    class _DataUpdateCoordinator:
        def __init__(self, hass=None, logger=None, name=None, update_interval=None, *args, **kwargs):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None
            self.async_set_updated_data = Mock()
            self.async_request_refresh = Mock()

    mock_ha.helpers.update_coordinator = Mock()
    mock_ha.helpers.update_coordinator.DataUpdateCoordinator = _DataUpdateCoordinator
    mock_ha.helpers.update_coordinator.CoordinatorEntity = _CoordinatorEntity
    mock_ha.helpers.entity = Mock()
    # DeviceInfo is used with keyword args (identifiers=, name=, etc.)
    class _DeviceInfo:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    mock_ha.helpers.entity.DeviceInfo = _DeviceInfo
    mock_ha.helpers.entity_platform = Mock()
    mock_ha.helpers.entity_platform.AddEntitiesCallback = Mock()
    mock_ha.data_entry_flow = Mock()
    mock_ha.data_entry_flow.FlowResultType = Mock()
    mock_ha.data_entry_flow.FlowResultType.FORM = "form"
    mock_ha.data_entry_flow.FlowResultType.CREATE_ENTRY = "create_entry"
    for name, mod in [
        ("homeassistant", mock_ha),
        ("homeassistant.core", mock_ha.core),
        ("homeassistant.config_entries", mock_ha.config_entries),
        ("homeassistant.const", mock_ha.const),
        ("homeassistant.helpers", mock_ha.helpers),
        ("homeassistant.helpers.entity_registry", mock_ha.helpers.entity_registry),
        ("homeassistant.helpers.device_registry", mock_ha.helpers.device_registry),
        ("homeassistant.components", mock_ha.components),
        ("homeassistant.components.light", mock_ha.components.light),
        ("homeassistant.components.button", mock_ha.components.button),
        ("homeassistant.components.mqtt", mock_ha.components.mqtt),
        ("homeassistant.helpers.update_coordinator", mock_ha.helpers.update_coordinator),
        ("homeassistant.helpers.entity", mock_ha.helpers.entity),
        ("homeassistant.helpers.entity_platform", mock_ha.helpers.entity_platform),
        ("homeassistant.data_entry_flow", mock_ha.data_entry_flow),
    ]:
        sys.modules[name] = mod
