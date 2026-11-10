from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from custom_components.play24 import (
    PLATFORMS,
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
    update_listener,
)
from custom_components.play24.api import Play24AuthError, Play24ConnectionError
from custom_components.play24.const import (
    CONF_JSESSIONID,
    CONF_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


def test_platforms_definition():
    """Test that PLATFORMS contains only entity platforms and excludes diagnostics."""
    assert PLATFORMS == ["sensor"]
    assert "diagnostics" not in PLATFORMS


@pytest.mark.asyncio
async def test_init_setup_auth_failed():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {CONF_JSESSIONID: "bad_session"}

    with patch("custom_components.play24.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(
            side_effect=Play24AuthError("Session expired")
        )

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
        instance.async_test_connection = AsyncMock(
            side_effect=Play24ConnectionError("Timeout")
        )

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
    entry.data = {CONF_JSESSIONID: "valid_session", "dwrsessionid": "custom_dwr"}

    with patch("custom_components.play24.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)

        with patch(
            "custom_components.play24.Play24DataUpdateCoordinator"
        ) as mock_coord_cls:
            mock_coord = mock_coord_cls.return_value
            mock_coord.async_config_entry_first_refresh = AsyncMock()

            result = await async_setup_entry(hass, entry)
            assert result is True
            assert DOMAIN in hass.data
            assert entry.entry_id in hass.data[DOMAIN]
            mock_client.assert_called_once()
            _, kwargs = mock_client.call_args
            assert kwargs.get("dwrsessionid") == "custom_dwr"
            hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
                entry, ["sensor"]
            )
            assert (
                "diagnostics"
                not in hass.config_entries.async_forward_entry_setups.call_args[0][1]
            )
            entry.async_on_unload.assert_called_once()
            entry.add_update_listener.assert_called_once_with(update_listener)


@pytest.mark.asyncio
async def test_update_listener_updates_coordinator_interval():
    """Test update_listener updates coordinator update_interval."""
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.update_interval = timedelta(hours=6)
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {CONF_SCAN_INTERVAL_HOURS: 12}
    hass.data = {DOMAIN: {entry.entry_id: coordinator}}

    await update_listener(hass, entry)
    assert coordinator.update_interval == timedelta(hours=12)


@pytest.mark.asyncio
async def test_update_listener_fallback_to_scan_interval():
    """Test update_listener falls back to scan_interval legacy key."""
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.update_interval = timedelta(hours=6)
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {CONF_SCAN_INTERVAL: 3}
    hass.data = {DOMAIN: {entry.entry_id: coordinator}}

    await update_listener(hass, entry)
    assert coordinator.update_interval == timedelta(hours=3)


@pytest.mark.asyncio
async def test_update_listener_invalid_value_falls_back_to_default():
    """Test update_listener falls back to DEFAULT_SCAN_INTERVAL on invalid options."""
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.update_interval = timedelta(hours=1)
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {CONF_SCAN_INTERVAL_HOURS: "not_a_number"}
    hass.data = {DOMAIN: {entry.entry_id: coordinator}}

    await update_listener(hass, entry)
    assert coordinator.update_interval == DEFAULT_SCAN_INTERVAL


@pytest.mark.asyncio
async def test_update_listener_missing_entry_in_hass_data():
    """Test update_listener handles entry not present in hass.data."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    entry = MagicMock()
    entry.entry_id = "not_found"
    entry.options = {CONF_SCAN_INTERVAL_HOURS: 12}

    # Should not raise exception
    await update_listener(hass, entry)


@pytest.mark.asyncio
async def test_init_reload_entry():
    """Test async_reload_entry triggers config entry reload."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_reload = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "test_entry_options_reload"

    await async_reload_entry(hass, entry)
    hass.config_entries.async_reload.assert_awaited_once_with("test_entry_options_reload")



@pytest.mark.asyncio
async def test_init_unload_success():
    hass = MagicMock()
    hass.data = {DOMAIN: {"test_entry": MagicMock()}}
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    entry = MagicMock()
    entry.entry_id = "test_entry"

    result = await async_unload_entry(hass, entry)
    assert result is True
    assert "test_entry" not in hass.data[DOMAIN]
    hass.config_entries.async_unload_platforms.assert_awaited_once_with(
        entry, ["sensor"]
    )
    assert (
        "diagnostics"
        not in hass.config_entries.async_unload_platforms.call_args[0][1]
    )
