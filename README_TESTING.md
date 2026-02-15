# Testing the Hafele Local MQTT Integration

## Setup

To run the tests, you have two options:

### Option 1: Install Home Assistant (Recommended)

This is the standard approach for testing Home Assistant custom integrations:

```bash
# Install test dependencies including Home Assistant
pip install -r requirements_test.txt
```

### Option 2: Use Mocked Home Assistant (Lightweight)

If you don't want to install the full Home Assistant package, the tests use mocked Home Assistant modules. However, you may need to ensure the mocks are set up correctly.

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=custom_components.hafele_local_mqtt --cov-report=html

# Run a specific test file
pytest tests/test_light.py -v

# Run a specific test
pytest tests/test_light.py::test_light_is_on -v
```

## Test Structure

Tests live in the top-level **`tests/`** directory (not inside `custom_components/`) so they are not bundled when you copy or zip the integration for installation (e.g. HACS or manual install).

- **`conftest.py`** (project root) - Mocks Home Assistant modules so tests run without installing HA
- **`tests/conftest.py`** - Shared fixtures (mock_hass, mock_mqtt_client, etc.)
- **`tests/test_light.py`** - Light platform tests
- **`tests/test_discovery.py`** - Discovery tests
- **`tests/test_mqtt_client.py`** - MQTT client tests
- **`tests/test_config_flow.py`** - Config flow tests
- **`tests/test_button.py`** - Button platform tests
- **`tests/test_init.py`** - Integration setup tests

## Troubleshooting

If you get `ModuleNotFoundError: No module named 'homeassistant'`:

1. **Option A**: Install Home Assistant:
   ```bash
   pip install homeassistant>=2024.1.0
   ```

2. **Option B**: Ensure the mock setup runs first—`conftest.py` at the project root installs HA mocks before any test or integration code loads.

3. **Option C**: Use a virtual environment with Home Assistant installed for testing.

