from datetime import datetime
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from homeassistant.core import HomeAssistant
from custom_components.play24.coordinator import Play24DataUpdateCoordinator
from custom_components.play24.api import Play24Client, Play24DataError, Play24AuthError
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed

@pytest.mark.asyncio
async def test_coordinator_sequential_update():
    hass = AsyncMock()
    client = AsyncMock()
    client.async_change_account_context = AsyncMock()
    
    client.async_get_context_msisdns = AsyncMock(return_value=["123", "456"])
    client.async_get_other_tile = AsyncMock(return_value={"device": "Phone", "tariff": "Test"})
    client.async_get_components_list = AsyncMock(return_value=["Service 1"])
    
    coordinator = Play24DataUpdateCoordinator(hass, client)
    
    data = await coordinator._async_update_data()
    
    assert "123" in data
    assert "456" in data
    assert data["123"]["tariff"] == "Test"
    assert coordinator.last_update_success_time is not None
    assert isinstance(coordinator.last_update_success_time, datetime)
    
    # Assert change_account_context was called for each MSISDN
    assert client.async_change_account_context.call_count == 2
    client.async_change_account_context.assert_any_call("123")
    client.async_change_account_context.assert_any_call("456")

@pytest.mark.asyncio
async def test_coordinator_fallback_to_other_tile():
    hass = AsyncMock()
    client = AsyncMock()
    client.async_change_account_context = AsyncMock()
    
    # get_context_msisdns returns empty list (e.g. 1-number account)
    client.async_get_context_msisdns = AsyncMock(return_value=[])
    client.async_get_other_tile = AsyncMock(return_value={"device": "Xiaomi", "tariff": "Karta", "msisdn": "48 501 234 567"})
    client.async_get_components_list = AsyncMock(return_value=["Pakiety"])
    
    coordinator = Play24DataUpdateCoordinator(hass, client)
    data = await coordinator._async_update_data()
    
    assert "501234567" in data
    assert data["501234567"]["device"] == "Xiaomi"
    assert data["501234567"]["tariff"] == "Karta"
    assert coordinator.last_update_success_time is not None

@pytest.mark.asyncio
async def test_coordinator_context_switch_failure_skips_number_initially():
    hass = AsyncMock()
    client = AsyncMock()
    
    client.async_get_context_msisdns = AsyncMock(return_value=["111", "222", "333"])
    
    # Mock change_account_context: fails for "222"
    async def mock_change_context(msisdn):
        if msisdn == "222":
            raise Play24DataError("Context switch failed for 222")
        return None

    client.async_change_account_context = AsyncMock(side_effect=mock_change_context)
    
    async def mock_other_tile():
        return {"device": "Phone", "tariff": "Tariff for current context"}
    
    client.async_get_other_tile = AsyncMock(side_effect=mock_other_tile)
    client.async_get_components_list = AsyncMock(return_value=["Active Service"])
    
    coordinator = Play24DataUpdateCoordinator(hass, client)
    data = await coordinator._async_update_data()
    
    # 111 and 333 should be in data
    assert "111" in data
    assert "333" in data
    # 222 failed context switch with no prior data, so it must not be in data
    assert "222" not in data
    assert len(data) == 2

@pytest.mark.asyncio
async def test_coordinator_transient_failure_retains_previous_data():
    hass = AsyncMock()
    client = AsyncMock()
    client.async_get_context_msisdns = AsyncMock(return_value=["111", "222"])
    client.async_change_account_context = AsyncMock()
    client.async_get_other_tile = AsyncMock(side_effect=[
        {"device": "Phone 1", "tariff": "Tariff 1"},
        {"device": "Phone 2", "tariff": "Tariff 2"},
    ])
    client.async_get_components_list = AsyncMock(return_value=["Active Service"])

    coordinator = Play24DataUpdateCoordinator(hass, client)
    first_data = await coordinator._async_update_data()
    assert "111" in first_data
    assert "222" in first_data
    coordinator.data = first_data

    # Second refresh: "222" context switch fails transiently
    async def mock_change_context_second(msisdn):
        if msisdn == "222":
            raise Play24DataError("Transient error for 222")
        return None

    client.async_change_account_context = AsyncMock(side_effect=mock_change_context_second)
    client.async_get_other_tile = AsyncMock(return_value={"device": "Phone 1 Refreshed", "tariff": "Tariff 1"})

    second_data = await coordinator._async_update_data()
    assert second_data["111"]["device"] == "Phone 1 Refreshed"
    # 222 was retained from previous good data
    assert "222" in second_data
    assert second_data["222"]["device"] == "Phone 2"

@pytest.mark.asyncio
async def test_coordinator_empty_discovery_is_update_failed():
    hass = AsyncMock()
    client = AsyncMock()
    client.async_get_context_msisdns = AsyncMock(return_value=[])
    client.async_get_other_tile = AsyncMock(return_value={})
    coordinator = Play24DataUpdateCoordinator(hass, client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

@pytest.mark.asyncio
async def test_coordinator_auth_error_is_not_swallowed_during_context_switch():
    hass = AsyncMock()
    client = AsyncMock()
    client.async_get_context_msisdns = AsyncMock(return_value=["123456789"])
    client.async_change_account_context = AsyncMock(side_effect=Play24AuthError("expired"))
    coordinator = Play24DataUpdateCoordinator(hass, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_expanded_entities_data():
    hass = AsyncMock()
    client = AsyncMock()
    client.async_get_context_msisdns = AsyncMock(return_value=["506191196", "500111222"])
    client.async_change_account_context = AsyncMock()
    client.async_get_messages = AsyncMock(return_value={"unread_messages": 2})

    async def mock_other_tile():
        return {
            "device": "Xiaomi Redmi Note 12 Pro 5G",
            "tariff": "GRUPA L",
            "billing_cycle": "20. dzień miesiąca",
            "billing_cycle_day": 20,
            "remaining_cycle_days": 12,
            "offer_details": "Oferta Główna",
            "group_owner_msisdn": "506191196",
        }

    async def mock_components(category):
        return ["Pakiet 10 GB", "Roaming UE", "Darmowe minuty"]

    async def mock_finance():
        return {
            "last_invoice_amount": "245,28 zł",
            "invoice_amount_value": 245.28,
            "invoice_due_date": "2026-10-06",
            "invoice_number": "F/30832084/09/26",
            "invoice_date": "2026-09-22",
            "payment_status": "Dokument opłacony",
            "account_balance": None,
        }

    client.async_get_other_tile = AsyncMock(side_effect=mock_other_tile)
    client.async_get_components_list = AsyncMock(side_effect=mock_components)
    client.async_get_finance_tile = AsyncMock(side_effect=mock_finance)

    coordinator = Play24DataUpdateCoordinator(hass, client)
    data = await coordinator._async_update_data()

    assert len(data) == 2
    assert "506191196" in data
    mdata = data["506191196"]
    assert mdata["data_package_gb"] == 10.0
    assert mdata["invoice_amount_value"] == 245.28
    assert mdata["invoice_due_date"] == "2026-10-06"
    assert mdata["payment_status"] == "Dokument opłacony"
    assert mdata["remaining_cycle_days"] == 12

    assert coordinator.account_data["unread_messages"] == 2
    assert coordinator.account_data["total_msisdns"] == 2
    assert coordinator.account_data["successful_msisdns"] == 2
    assert coordinator.account_data["invoice_amount_value"] == 245.28
    assert coordinator.account_data["invoice_number"] == "F/30832084/09/26"

