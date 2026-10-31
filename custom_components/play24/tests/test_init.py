import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from custom_components.play24 import async_setup_entry, async_unload_entry
from custom_components.play24.api import Play24AuthError, Play24ConnectionError
from custom_components.play24.const import DOMAIN, CONF_JSESSIONID

@pytest.mark.asyncio
async def test_init_setup_auth_failed():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {CONF_JSESSIONID: "bad_session"}

    with patch("custom_components.play24.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(side_effect=Play24AuthError("Session expired"))

        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)

@pytest.mark.asyncio
async def test_init_setup_connection_error_raises_not_ready():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {CONF_JSESSIONID: "valid_session"}

    with patch("custom_components.play24.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(side_effect=Play24ConnectionError("Timeout"))

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)

@pytest.mark.asyncio
async def test_init_setup_success():
    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {CONF_JSESSIONID: "valid_session"}

    with patch("custom_components.play24.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)

        with patch("custom_components.play24.Play24DataUpdateCoordinator") as mock_coord_cls:
            mock_coord = mock_coord_cls.return_value
            mock_coord.async_config_entry_first_refresh = AsyncMock()

            result = await async_setup_entry(hass, entry)
            assert result is True
            assert DOMAIN in hass.data
            assert entry.entry_id in hass.data[DOMAIN]

