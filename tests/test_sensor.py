from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.play24.const import DOMAIN
from custom_components.play24.sensor import (
    Play24AccountBalanceSensor,
    Play24AccountInvoiceAmountSensor,
    Play24AccountInvoiceDueDateSensor,
    Play24AccountMsisdnsSensor,
    Play24AccountPaymentStatusSensor,
    Play24AccountValiditySensor,
    Play24ActiveComponentsSensor,
    Play24BillingCycleRemainingDaysSensor,
    Play24BillingCycleSensor,
    Play24DataLimitSensor,
    Play24InvoiceDueDateSensor,
    Play24LastInvoiceAmountSensor,
    Play24LastUpdateSensor,
    Play24PaymentStatusSensor,
    Play24SuccessfulMsisdnsSensor,
    Play24TariffSensor,
    Play24UnreadMessagesSensor,
    _classify_tariff,
    async_setup_entry,
)


@pytest.fixture
def mock_coordinator():
    coord = MagicMock()
    coord.config_entry.entry_id = "test_entry_id"
    coord.last_update_success_time = datetime(2026, 10, 12, 10, 0, 0, tzinfo=UTC)
    coord.data = {
        "500123456": {
            "msisdn": "500123456",
            "device": "Xiaomi Redmi Note 12",
            "tariff": "GRUPA L",
            "billing_cycle": None,
            "active_components": ["Darmowe minuty", "Roaming"],
        },
        "500654321": {
            "msisdn": "500654321",
            "device": "Brovi 5G CPE",
            "tariff": "Play na Kartę odNOWA",
            "billing_cycle": None,
            "active_components": ["Pakiet Internet"],
        },
    }
    return coord


@pytest.mark.asyncio
async def test_sensors_creation_and_values(mock_coordinator):
    msisdn = "500123456"
    msisdn_data = mock_coordinator.data[msisdn]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, msisdn)},
        name=f"Play24 {msisdn}",
        manufacturer="Play",
        model=msisdn_data.get("device"),
        sw_version=msisdn_data.get("tariff"),
        via_device=(DOMAIN, "test_entry_id"),
    )

    # 1. Tariff sensor (Postpaid)
    tariff_sensor = Play24TariffSensor(mock_coordinator, device_info, msisdn)
    assert tariff_sensor.name == "Taryfa"
    assert tariff_sensor.native_value == "GRUPA L"
    assert tariff_sensor.unique_id == "test_entry_id_500123456_tariff"
    assert "taryfa" not in tariff_sensor.extra_state_attributes
    assert "numer" not in tariff_sensor.extra_state_attributes
    assert "urzadzenie" not in tariff_sensor.extra_state_attributes
    assert tariff_sensor.extra_state_attributes["typ_taryfy"] == "postpaid"
    assert tariff_sensor._attr_device_info.get("via_device") == (
        DOMAIN,
        "test_entry_id",
    )

    # 2. Tariff sensor (Prepaid)
    msisdn_prep = "500654321"
    prep_data = mock_coordinator.data[msisdn_prep]
    prep_device_info = DeviceInfo(
        identifiers={(DOMAIN, msisdn_prep)},
        name=f"Play24 {msisdn_prep}",
        manufacturer="Play",
        model=prep_data.get("device"),
        sw_version=prep_data.get("tariff"),
        via_device=(DOMAIN, "test_entry_id"),
    )
    prep_tariff_sensor = Play24TariffSensor(
        mock_coordinator, prep_device_info, msisdn_prep
    )
    assert prep_tariff_sensor.native_value == "Play na Kartę odNOWA"
    assert prep_tariff_sensor.extra_state_attributes["typ_taryfy"] == "prepaid"

    # 3. Active components sensor
    comp_sensor = Play24ActiveComponentsSensor(mock_coordinator, device_info, msisdn)
    assert comp_sensor.name == "Aktywne usługi"
    assert comp_sensor.native_value == 2
    assert comp_sensor.unique_id == "test_entry_id_500123456_active_components"
    assert comp_sensor.extra_state_attributes["uslugi"] == ["Darmowe minuty", "Roaming"]

    # 4. Billing cycle sensor - must return None when None
    cycle_sensor = Play24BillingCycleSensor(mock_coordinator, device_info, msisdn)
    assert cycle_sensor.name == "Cykl rozliczeniowy"
    assert cycle_sensor.native_value is None
    assert cycle_sensor.unique_id == "test_entry_id_500123456_billing_cycle"

    # 5. Account active msisdns count sensor
    parent_device_info = DeviceInfo(
        identifiers={(DOMAIN, "test_entry_id")},
        name="Konto Play24",
        manufacturer="Play",
        model="Play24 Account",
    )
    account_sensor = Play24AccountMsisdnsSensor(
        mock_coordinator, parent_device_info, "test_entry_id"
    )
    assert account_sensor.name == "Liczba aktywnych numerów"
    assert account_sensor.native_value == 2
    assert account_sensor.unique_id == "test_entry_id_active_msisdns_count"

    # 6. Account last update sensor
    last_update_sensor = Play24LastUpdateSensor(
        mock_coordinator, parent_device_info, "test_entry_id"
    )
    assert last_update_sensor.name == "Ostatnia aktualizacja"
    assert last_update_sensor.native_value == datetime(
        2026, 10, 12, 10, 0, 0, tzinfo=UTC
    )
    assert last_update_sensor.unique_id == "test_entry_id_last_update"
    assert last_update_sensor.device_class == "timestamp"
    assert last_update_sensor.entity_category == "diagnostic"


def test_classify_tariff():
    assert _classify_tariff("GRUPA L") == "postpaid"
    assert _classify_tariff("Abonament M") == "postpaid"
    assert _classify_tariff("Biznes Box") == "postpaid"
    assert _classify_tariff("Play na Kartę odNOWA") == "prepaid"
    assert _classify_tariff("Play na Kartę 3.0") == "prepaid"
    assert _classify_tariff("Play na kartę PL 2.1") == "prepaid"
    assert _classify_tariff("") == "unknown"
    assert _classify_tariff(None) == "unknown"


@pytest.mark.asyncio
async def test_async_setup_entry_hierarchy():
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "entry_123"

    coord = MagicMock()
    coord.config_entry = entry
    coord.last_update_success_time = datetime(2026, 10, 12, 10, 0, 0, tzinfo=UTC)
    coord.account_data = {}
    coord.data = {
        "123456789": {
            "device": "Samsung S21",
            "tariff": "Abonament M",
            "billing_cycle": "15. dzień miesiąca",
            "active_components": ["5G"],
        }
    }
    hass.data = {DOMAIN: {entry.entry_id: coord}}

    added_entities = []

    def mock_add_entities(entities):
        added_entities.extend(entities)

    await async_setup_entry(hass, entry, mock_add_entities)

    # Entities: 4 parent account sensors + 7 child sensors = 11 total
    assert len(added_entities) == 11

    # Verify parent device info on account sensor
    parent_entity = added_entities[0]
    assert parent_entity.device_info["identifiers"] == {(DOMAIN, "entry_123")}
    assert parent_entity.device_info["model"] == "Play24 Account"
    assert parent_entity.device_info["configuration_url"] == "https://24.play.pl"

    # Verify child device info and via_device link to parent on MSISDN sensor
    child_entity = next(
        e for e in added_entities if getattr(e, "msisdn", None) == "123456789"
    )
    assert child_entity.device_info["identifiers"] == {(DOMAIN, "123456789")}
    assert child_entity.device_info["model"] == "Samsung S21"
    assert child_entity.device_info["via_device"] == (DOMAIN, "entry_123")

    # Check unique IDs
    unique_ids = [e.unique_id for e in added_entities]
    assert "entry_123_active_msisdns_count" in unique_ids
    assert "entry_123_successful_msisdns_count" in unique_ids
    assert "entry_123_last_update" in unique_ids
    assert "entry_123_unread_messages" in unique_ids
    assert "entry_123_123456789_tariff" in unique_ids
    assert "entry_123_123456789_active_components" in unique_ids
    assert "entry_123_123456789_billing_cycle" in unique_ids
    assert "entry_123_123456789_remaining_cycle_days" in unique_ids
    assert "entry_123_123456789_last_invoice_amount" in unique_ids
    assert "entry_123_123456789_invoice_due_date" in unique_ids
    assert "entry_123_123456789_payment_status" in unique_ids


@pytest.mark.asyncio
async def test_postpaid_expanded_sensors():
    coord = MagicMock()
    coord.config_entry.entry_id = "test_entry"
    coord.data = {
        "500000001": {
            "msisdn": "500000001",
            "device": "Xiaomi Redmi Note 12 Pro 5G",
            "tariff": "GRUPA L",
            "offer_details": "VIP Oferta POKOLENIA - NUMER GŁÓWNY",
            "group_owner_msisdn": "500000001",
            "billing_cycle": "20. dzień miesiąca",
            "billing_cycle_day": 20,
            "remaining_cycle_days": 12,
            "active_components": ["Pakiet 10 GB", "Roaming"],
            "data_package_gb": 10.0,
            "last_invoice_amount": "245,28 zł",
            "invoice_amount_value": 245.28,
            "invoice_due_date": "2026-10-06",
            "invoice_number": "F/00000000/01/26",
            "invoice_date": "2026-09-22",
            "payment_status": "Dokument opłacony",
        }
    }
    device_info = DeviceInfo(identifiers={(DOMAIN, "500000001")})

    # 1. Tariff with offer details and group owner attributes
    tariff_sensor = Play24TariffSensor(coord, device_info, "500000001")
    assert tariff_sensor.native_value == "GRUPA L"
    assert tariff_sensor.extra_state_attributes["typ_taryfy"] == "postpaid"
    assert (
        tariff_sensor.extra_state_attributes["szczegoly_oferty"]
        == "VIP Oferta POKOLENIA - NUMER GŁÓWNY"
    )
    assert tariff_sensor.extra_state_attributes["numer_glowny"] == "500000001"

    # 2. Billing cycle with day attribute
    cycle_sensor = Play24BillingCycleSensor(coord, device_info, "500000001")
    assert cycle_sensor.native_value == "20. dzień miesiąca"
    assert cycle_sensor.extra_state_attributes["dzien_cyklu"] == 20

    # 3. Remaining cycle days
    rem_sensor = Play24BillingCycleRemainingDaysSensor(coord, device_info, "500000001")
    assert rem_sensor.native_value == 12
    assert rem_sensor.native_unit_of_measurement == "d"
    assert rem_sensor.icon == "mdi:calendar-clock"

    # 4. Data package limit
    data_sensor = Play24DataLimitSensor(coord, device_info, "500000001")
    assert data_sensor.native_value == 10.0
    assert data_sensor.native_unit_of_measurement == "GB"
    assert data_sensor.device_class == "data_size"

    # 5. Last invoice amount
    inv_sensor = Play24LastInvoiceAmountSensor(coord, device_info, "500000001")
    assert inv_sensor.native_value == 245.28
    assert inv_sensor.native_unit_of_measurement == "PLN"
    assert inv_sensor.device_class == "monetary"
    assert inv_sensor.extra_state_attributes["numer_faktury"] == "F/00000000/01/26"
    assert inv_sensor.extra_state_attributes["data_wystawienia"] == "2026-09-22"
    assert inv_sensor.extra_state_attributes["kwota_oryginalna"] == "245,28 zł"

    # 6. Due date
    due_sensor = Play24InvoiceDueDateSensor(coord, device_info, "500000001")
    assert due_sensor.native_value == "2026-10-06"
    assert due_sensor.device_class == "date"

    # 7. Payment status
    status_sensor = Play24PaymentStatusSensor(coord, device_info, "500000001")
    assert status_sensor.native_value == "Dokument opłacony"


@pytest.mark.asyncio
async def test_prepaid_expanded_sensors():
    coord = MagicMock()
    coord.config_entry.entry_id = "test_entry"
    coord.data = {
        "500999888": {
            "msisdn": "500999888",
            "device": "Brovi 5G CPE",
            "tariff": "Play na Kartę odNOWA",
            "active_components": [],
            "account_balance": 25.50,
            "account_validity": "2026-12-31",
            "outgoing_validity": "2026-11-30",
        }
    }
    device_info = DeviceInfo(identifiers={(DOMAIN, "500999888")})

    # Balance sensor
    balance_sensor = Play24AccountBalanceSensor(coord, device_info, "500999888")
    assert balance_sensor.native_value == 25.50
    assert balance_sensor.native_unit_of_measurement == "PLN"
    assert balance_sensor.device_class == "monetary"

    # Validity sensor
    validity_sensor = Play24AccountValiditySensor(coord, device_info, "500999888")
    assert validity_sensor.native_value == "2026-11-30"
    assert validity_sensor.device_class == "date"
    assert validity_sensor.extra_state_attributes["waznosc_konta"] == "2026-12-31"


@pytest.mark.asyncio
async def test_account_invoice_sensors():
    coord = MagicMock()
    coord.account_data = {
        "invoice_amount_value": 312.40,
        "last_invoice_amount": "312,40 zł",
        "invoice_number": "F/999/2026",
        "invoice_due_date": "2026-11-15",
        "payment_status": "Opłacony",
        "unread_messages": 3,
        "successful_msisdns": 2,
    }
    device_info = DeviceInfo(identifiers={(DOMAIN, "test_account")})

    inv_sensor = Play24AccountInvoiceAmountSensor(coord, device_info, "test_entry")
    assert inv_sensor.native_value == 312.40
    assert inv_sensor.native_unit_of_measurement == "PLN"
    assert inv_sensor.device_class == "monetary"
    assert inv_sensor.state_class is None
    assert inv_sensor.extra_state_attributes["numer_faktury"] == "F/999/2026"

    due_sensor = Play24AccountInvoiceDueDateSensor(coord, device_info, "test_entry")
    assert due_sensor.native_value == "2026-11-15"
    assert due_sensor.device_class == "date"

    stat_sensor = Play24AccountPaymentStatusSensor(coord, device_info, "test_entry")
    assert stat_sensor.native_value == "Opłacony"

    msg_sensor = Play24UnreadMessagesSensor(coord, device_info, "test_entry")
    assert msg_sensor.native_value == 3

    succ_sensor = Play24SuccessfulMsisdnsSensor(coord, device_info, "test_entry")
    assert succ_sensor.native_value == 2
    assert succ_sensor.entity_category == "diagnostic"


@pytest.mark.asyncio
async def test_async_setup_entry_dynamic_msisdn_discovery():
    """Test dynamic registration of sensors when a new MSISDN appears on coordinator update."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    listeners = []
    coord = MagicMock()
    coord.config_entry = entry
    coord.last_update_success_time = datetime(2026, 10, 12, 10, 0, 0, tzinfo=UTC)
    coord.account_data = {}
    coord.data = {
        "500111222": {
            "msisdn": "500111222",
            "device": "Phone A",
            "tariff": "Abonament",
            "billing_cycle": None,
            "active_components": [],
        }
    }

    def mock_add_listener(cb):
        listeners.append(cb)

        def remove_cb():
            if cb in listeners:
                listeners.remove(cb)

        return remove_cb

    coord.async_add_listener.side_effect = mock_add_listener
    hass.data = {DOMAIN: {entry.entry_id: coord}}

    added_batches: list[list] = []

    def mock_add_entities(entities):
        added_batches.append(list(entities))

    await async_setup_entry(hass, entry, mock_add_entities)

    # 1. Initial setup verification
    assert len(added_batches) == 1
    initial_entities = added_batches[0]
    initial_msisdns = {
        getattr(e, "msisdn", None) for e in initial_entities if hasattr(e, "msisdn")
    }
    assert "500111222" in initial_msisdns
    assert "500999888" not in initial_msisdns

    # Coordinator listener and unload hook registered
    coord.async_add_listener.assert_called_once()
    assert len(listeners) == 1
    entry.async_on_unload.assert_called_once()

    # 2. Coordinator refreshes data with a newly added MSISDN
    coord.data["500999888"] = {
        "msisdn": "500999888",
        "device": "Phone B",
        "tariff": "Play na Kartę",
        "account_balance": 15.0,
        "active_components": [],
    }

    # Trigger coordinator listener
    listeners[0]()

    # Verify async_add_entities called a second time with the new MSISDN's sensors
    assert len(added_batches) == 2
    new_batch = added_batches[1]
    new_msisdns = {
        getattr(e, "msisdn", None) for e in new_batch if hasattr(e, "msisdn")
    }
    assert "500999888" in new_msisdns
    assert "500111222" not in new_msisdns

    # 3. Subsequent update with no new MSISDNs should not trigger another add_entities call
    listeners[0]()
    assert len(added_batches) == 2


@pytest.mark.asyncio
async def test_async_setup_entry_dynamic_invoice_discovery():
    """Test dynamic registration of account invoice sensors when invoice data appears later."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    listeners = []
    coord = MagicMock()
    coord.config_entry = entry
    coord.last_update_success_time = datetime(2026, 10, 12, 10, 0, 0, tzinfo=UTC)
    coord.account_data = {}
    coord.data = {
        "500111222": {
            "msisdn": "500111222",
            "device": "Phone A",
            "tariff": "Abonament",
            "active_components": [],
        }
    }
    coord.async_add_listener.side_effect = lambda cb: (
        listeners.append(cb),
        lambda: listeners.remove(cb),
    )[1]
    hass.data = {DOMAIN: {entry.entry_id: coord}}

    added_batches: list[list] = []

    def mock_add_entities(entities):
        added_batches.append(list(entities))

    await async_setup_entry(hass, entry, mock_add_entities)

    assert len(added_batches) == 1
    # Check that account invoice amount sensor was NOT added initially
    assert not any(
        isinstance(e, Play24AccountInvoiceAmountSensor) for e in added_batches[0]
    )

    # Now invoice data arrives in coordinator
    coord.account_data = {
        "invoice_amount_value": 89.90,
        "last_invoice_amount": "89,90 zł",
        "invoice_due_date": "2026-11-20",
        "payment_status": "Do zapłaty",
    }

    listeners[0]()

    assert len(added_batches) == 2
    assert any(
        isinstance(e, Play24AccountInvoiceAmountSensor) for e in added_batches[1]
    )
    assert any(
        isinstance(e, Play24AccountInvoiceDueDateSensor) for e in added_batches[1]
    )
    assert any(
        isinstance(e, Play24AccountPaymentStatusSensor) for e in added_batches[1]
    )

    # Next update should not duplicate account invoice sensors
    listeners[0]()
    assert len(added_batches) == 2


@pytest.mark.asyncio
async def test_async_setup_entry_dynamic_msisdn_discovery_empty_start():
    """Test dynamic registration when coordinator starts empty and multiple MSISDNs arrive later."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    listeners = []
    coord = MagicMock()
    coord.config_entry = entry
    coord.last_update_success_time = datetime(2026, 10, 12, 10, 0, 0, tzinfo=UTC)
    coord.account_data = {}
    coord.data = {}

    coord.async_add_listener.side_effect = lambda cb: (
        listeners.append(cb),
        lambda: listeners.remove(cb),
    )[1]
    hass.data = {DOMAIN: {entry.entry_id: coord}}

    added_batches: list[list] = []

    def mock_add_entities(entities):
        added_batches.append(list(entities))

    await async_setup_entry(hass, entry, mock_add_entities)

    # Initial setup: only account-level parent sensors (4 sensors)
    assert len(added_batches) == 1
    assert len(added_batches[0]) == 4
    assert not any(hasattr(e, "msisdn") for e in added_batches[0])

    # Coordinator update arrives with 2 new numbers
    coord.data = {
        "600111222": {
            "msisdn": "600111222",
            "device": "Phone X",
            "tariff": "Abonament",
            "active_components": [],
        },
        "600333444": {
            "msisdn": "600333444",
            "device": "Phone Y",
            "tariff": "Play na Kartę",
            "active_components": [],
        },
    }

    listeners[0]()

    # Second batch should contain sensors for both numbers
    assert len(added_batches) == 2
    batch2_msisdns = {
        getattr(e, "msisdn", None) for e in added_batches[1] if hasattr(e, "msisdn")
    }
    assert batch2_msisdns == {"600111222", "600333444"}

    # Another update without any new MSISDNs -> no additional add_entities call
    listeners[0]()
    assert len(added_batches) == 2


@pytest.mark.asyncio
async def test_async_setup_entry_dynamic_msisdn_discovery_none_start():
    """Test dynamic registration when coordinator data starts as None."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    listeners = []
    coord = MagicMock()
    coord.config_entry = entry
    coord.last_update_success_time = None
    coord.account_data = {}
    coord.data = None

    coord.async_add_listener.side_effect = lambda cb: (
        listeners.append(cb),
        lambda: listeners.remove(cb),
    )[1]
    hass.data = {DOMAIN: {entry.entry_id: coord}}

    added_batches: list[list] = []

    def mock_add_entities(entities):
        added_batches.append(list(entities))

    await async_setup_entry(hass, entry, mock_add_entities)

    assert len(added_batches) == 1
    assert len(added_batches[0]) == 4

    coord.data = {
        "700111222": {
            "msisdn": "700111222",
            "device": "Router LTE",
            "tariff": "Internet Biznes",
            "active_components": [],
        }
    }

    listeners[0]()

    assert len(added_batches) == 2
    batch2_msisdns = {
        getattr(e, "msisdn", None) for e in added_batches[1] if hasattr(e, "msisdn")
    }
    assert batch2_msisdns == {"700111222"}


@pytest.mark.asyncio
async def test_async_setup_entry_listener_unregistration():
    """Test that entry.async_on_unload is called with coordinator remove_listener."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    listeners = []
    coord = MagicMock()
    coord.config_entry = entry
    coord.data = {}
    coord.account_data = {}

    coord.async_add_listener.side_effect = lambda cb: (
        listeners.append(cb),
        lambda: listeners.remove(cb),
    )[1]
    hass.data = {DOMAIN: {entry.entry_id: coord}}

    await async_setup_entry(hass, entry, MagicMock())

    assert len(listeners) == 1
    entry.async_on_unload.assert_called_once()

    # Call unload callback
    unload_cb = entry.async_on_unload.call_args[0][0]
    unload_cb()
    assert len(listeners) == 0
