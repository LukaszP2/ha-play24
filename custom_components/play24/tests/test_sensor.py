from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.helpers.device_registry import DeviceInfo
from custom_components.play24.const import DOMAIN
from custom_components.play24.sensor import (
    async_setup_entry,
    Play24AccountMsisdnsSensor,
    Play24SuccessfulMsisdnsSensor,
    Play24LastUpdateSensor,
    Play24UnreadMessagesSensor,
    Play24AccountInvoiceAmountSensor,
    Play24AccountInvoiceDueDateSensor,
    Play24AccountPaymentStatusSensor,
    Play24TariffSensor,
    Play24ActiveComponentsSensor,
    Play24BillingCycleSensor,
    Play24BillingCycleRemainingDaysSensor,
    Play24DataLimitSensor,
    Play24LastInvoiceAmountSensor,
    Play24InvoiceDueDateSensor,
    Play24PaymentStatusSensor,
    Play24AccountBalanceSensor,
    Play24AccountValiditySensor,
    _classify_tariff,
)

@pytest.fixture
def mock_coordinator():
    coord = MagicMock()
    coord.config_entry.entry_id = "test_entry_id"
    coord.last_update_success_time = datetime(2026, 10, 12, 10, 0, 0, tzinfo=timezone.utc)
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
        }
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
    assert tariff_sensor._attr_device_info.get("via_device") == (DOMAIN, "test_entry_id")

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
    prep_tariff_sensor = Play24TariffSensor(mock_coordinator, prep_device_info, msisdn_prep)
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
    account_sensor = Play24AccountMsisdnsSensor(mock_coordinator, parent_device_info, "test_entry_id")
    assert account_sensor.name == "Liczba aktywnych numerów"
    assert account_sensor.native_value == 2
    assert account_sensor.unique_id == "test_entry_id_active_msisdns_count"

    # 6. Account last update sensor
    last_update_sensor = Play24LastUpdateSensor(mock_coordinator, parent_device_info, "test_entry_id")
    assert last_update_sensor.name == "Ostatnia aktualizacja"
    assert last_update_sensor.native_value == datetime(2026, 10, 12, 10, 0, 0, tzinfo=timezone.utc)
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
    coord.last_update_success_time = datetime(2026, 10, 12, 10, 0, 0, tzinfo=timezone.utc)
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
    
    mock_dev_reg = MagicMock()
    
    with pytest.MonkeyPatch.context() as mp:
        import custom_components.play24.sensor as sensor_mod
        mp.setattr(sensor_mod.dr, "async_get", lambda h: mock_dev_reg)
        
        added_entities = []
        def mock_add_entities(entities):
            added_entities.extend(entities)
            
        await async_setup_entry(hass, entry, mock_add_entities)
        
        # Parent account device and child phone device were registered
        assert mock_dev_reg.async_get_or_create.call_count == 2
        parent_call = mock_dev_reg.async_get_or_create.call_args_list[0].kwargs
        assert parent_call["identifiers"] == {(DOMAIN, "entry_123")}
        assert parent_call["model"] == "Play24 Account"

        child_call = mock_dev_reg.async_get_or_create.call_args_list[1].kwargs
        assert child_call["identifiers"] == {(DOMAIN, "123456789")}
        assert child_call["model"] == "Samsung S21"
        assert "via_device_id" in child_call
        
        # Entities: 4 parent account sensors + 7 child sensors = 11 total
        assert len(added_entities) == 11
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
        "506191196": {
            "msisdn": "506191196",
            "device": "Xiaomi Redmi Note 12 Pro 5G",
            "tariff": "GRUPA L",
            "offer_details": "VIP Oferta POKOLENIA - NUMER GŁÓWNY",
            "group_owner_msisdn": "506191196",
            "billing_cycle": "20. dzień miesiąca",
            "billing_cycle_day": 20,
            "remaining_cycle_days": 12,
            "active_components": ["Pakiet 10 GB", "Roaming"],
            "data_package_gb": 10.0,
            "last_invoice_amount": "245,28 zł",
            "invoice_amount_value": 245.28,
            "invoice_due_date": "2026-10-06",
            "invoice_number": "F/30832084/09/26",
            "invoice_date": "2026-09-22",
            "payment_status": "Dokument opłacony",
        }
    }
    device_info = DeviceInfo(identifiers={(DOMAIN, "506191196")})

    # 1. Tariff with offer details and group owner attributes
    tariff_sensor = Play24TariffSensor(coord, device_info, "506191196")
    assert tariff_sensor.native_value == "GRUPA L"
    assert tariff_sensor.extra_state_attributes["typ_taryfy"] == "postpaid"
    assert tariff_sensor.extra_state_attributes["szczegoly_oferty"] == "VIP Oferta POKOLENIA - NUMER GŁÓWNY"
    assert tariff_sensor.extra_state_attributes["numer_glowny"] == "506191196"

    # 2. Billing cycle with day attribute
    cycle_sensor = Play24BillingCycleSensor(coord, device_info, "506191196")
    assert cycle_sensor.native_value == "20. dzień miesiąca"
    assert cycle_sensor.extra_state_attributes["dzien_cyklu"] == 20

    # 3. Remaining cycle days
    rem_sensor = Play24BillingCycleRemainingDaysSensor(coord, device_info, "506191196")
    assert rem_sensor.native_value == 12
    assert rem_sensor.native_unit_of_measurement == "d"
    assert rem_sensor.icon == "mdi:calendar-clock"

    # 4. Data package limit
    data_sensor = Play24DataLimitSensor(coord, device_info, "506191196")
    assert data_sensor.native_value == 10.0
    assert data_sensor.native_unit_of_measurement == "GB"
    assert data_sensor.device_class == "data_size"

    # 5. Last invoice amount
    inv_sensor = Play24LastInvoiceAmountSensor(coord, device_info, "506191196")
    assert inv_sensor.native_value == 245.28
    assert inv_sensor.native_unit_of_measurement == "PLN"
    assert inv_sensor.device_class == "monetary"
    assert inv_sensor.extra_state_attributes["numer_faktury"] == "F/30832084/09/26"
    assert inv_sensor.extra_state_attributes["data_wystawienia"] == "2026-09-22"
    assert inv_sensor.extra_state_attributes["kwota_oryginalna"] == "245,28 zł"

    # 6. Due date
    due_sensor = Play24InvoiceDueDateSensor(coord, device_info, "506191196")
    assert due_sensor.native_value == "2026-10-06"
    assert due_sensor.device_class == "date"

    # 7. Payment status
    status_sensor = Play24PaymentStatusSensor(coord, device_info, "506191196")
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

