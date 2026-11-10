from unittest.mock import MagicMock

import pytest

from custom_components.play24.const import DOMAIN
from custom_components.play24.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.asyncio
async def test_diagnostics_redaction():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {"jsessionid": "super_secret_cookie"}

    coordinator = MagicMock()
    coordinator.account_data = {
        "invoice_number": "F/12345/01/26",
        "unread_messages": 3,
    }
    coordinator.data = {
        "500123456": {
            "msisdn": "500123456",
            "group_owner_msisdn": "500654321",
            "tariff": "Abonament",
        }
    }
    hass.data = {DOMAIN: {entry.entry_id: coordinator}}

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_data"]["jsessionid"] == "**REDACTED**"
    assert "***3456" in diagnostics["data"]
    assert diagnostics["data"]["***3456"]["msisdn"] == "***3456"
    assert diagnostics["data"]["***3456"]["group_owner_msisdn"] == "***4321"


@pytest.mark.asyncio
async def test_diagnostics_empty_data():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {"jsessionid": "super_secret_cookie"}

    coordinator = MagicMock()
    coordinator.account_data = {}
    coordinator.data = {}
    hass.data = {DOMAIN: {entry.entry_id: coordinator}}

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_data"]["jsessionid"] == "**REDACTED**"
    assert diagnostics["account_data"] == {}
    assert diagnostics["data"] == {}
