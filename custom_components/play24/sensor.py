import logging
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

def _classify_tariff(tariff: str | None) -> str:
    """Classify tariff into prepaid, postpaid or unknown."""
    if not tariff:
        return "unknown"
    t_lower = tariff.lower()
    if any(k in t_lower for k in ("kartę", "karcie", "odnowa", "karta", "prepaid")):
        return "prepaid"
    if any(k in t_lower for k in ("grupa", "abonament", "biznes", "postpaid", "mix")):
        return "postpaid"
    return "unknown"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Play24 sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    if not coordinator.data:
        return

    # Parent Account Device Info
    parent_device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Konto Play24",
        manufacturer="Play",
        model="Play24 Account",
        configuration_url="https://24.play.pl",
    )

    parent_device_id = None
    dev_reg = None
    try:
        dev_reg = dr.async_get(hass)
        parent_dev = dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name="Konto Play24",
            manufacturer="Play",
            model="Play24 Account",
            configuration_url="https://24.play.pl",
        )
        parent_device_id = getattr(parent_dev, 'id', None)
    except Exception as ex:
        _LOGGER.debug("Could not register parent account device: %s", ex)
        
    sensors: list[SensorEntity] = [
        Play24AccountMsisdnsSensor(coordinator, parent_device_info, entry.entry_id),
        Play24SuccessfulMsisdnsSensor(coordinator, parent_device_info, entry.entry_id),
        Play24LastUpdateSensor(coordinator, parent_device_info, entry.entry_id),
        Play24UnreadMessagesSensor(coordinator, parent_device_info, entry.entry_id),
    ]

    account_data = coordinator.account_data if (hasattr(coordinator, "account_data") and isinstance(coordinator.account_data, dict)) else {}

    # Account-level invoice sensors if invoice data is available
    if account_data.get("invoice_amount_value") is not None or account_data.get("last_invoice_amount") is not None:
        sensors.append(Play24AccountInvoiceAmountSensor(coordinator, parent_device_info, entry.entry_id))
        sensors.append(Play24AccountInvoiceDueDateSensor(coordinator, parent_device_info, entry.entry_id))
        sensors.append(Play24AccountPaymentStatusSensor(coordinator, parent_device_info, entry.entry_id))
    
    for msisdn, msisdn_data in coordinator.data.items():
        # Register child device linked to parent device via via_device_id
        if dev_reg and parent_device_id:
            try:
                dev_reg.async_get_or_create(
                    config_entry_id=entry.entry_id,
                    identifiers={(DOMAIN, msisdn)},
                    name=f"Play24 {msisdn}",
                    manufacturer="Play",
                    model=msisdn_data.get("device") or "Play24 Device",
                    via_device_id=parent_device_id,
                )
            except Exception as ex:
                _LOGGER.debug("Could not pre-register child device %s: %s", msisdn, ex)

        device_info = DeviceInfo(
            identifiers={(DOMAIN, msisdn)},
            name=f"Play24 {msisdn}",
            manufacturer="Play",
            model=msisdn_data.get("device") or "Play24 Device",
            via_device=(DOMAIN, entry.entry_id),
        )
        
        # Core child sensors
        sensors.append(Play24TariffSensor(coordinator, device_info, msisdn))
        sensors.append(Play24ActiveComponentsSensor(coordinator, device_info, msisdn))
        sensors.append(Play24BillingCycleSensor(coordinator, device_info, msisdn))

        # Remaining cycle days
        tariff_type = _classify_tariff(msisdn_data.get("tariff"))
        if msisdn_data.get("remaining_cycle_days") is not None or msisdn_data.get("billing_cycle") is not None or tariff_type == "postpaid":
            sensors.append(Play24BillingCycleRemainingDaysSensor(coordinator, device_info, msisdn))

        # Data package limit sensor
        if msisdn_data.get("data_package_gb") is not None:
            sensors.append(Play24DataLimitSensor(coordinator, device_info, msisdn))

        # Postpaid sensors
        if tariff_type == "postpaid" or msisdn_data.get("invoice_amount_value") is not None or msisdn_data.get("invoice_due_date") is not None:
            sensors.append(Play24LastInvoiceAmountSensor(coordinator, device_info, msisdn))
            sensors.append(Play24InvoiceDueDateSensor(coordinator, device_info, msisdn))
            sensors.append(Play24PaymentStatusSensor(coordinator, device_info, msisdn))

        # Prepaid sensors
        if tariff_type == "prepaid" or msisdn_data.get("account_balance") is not None or msisdn_data.get("outgoing_validity") is not None:
            sensors.append(Play24AccountBalanceSensor(coordinator, device_info, msisdn))
            sensors.append(Play24AccountValiditySensor(coordinator, device_info, msisdn))

    async_add_entities(sensors)


# =========================================================================
# ACCOUNT-LEVEL SENSORS (PARENT DEVICE)
# =========================================================================

class Play24AccountMsisdnsSensor(CoordinatorEntity, SensorEntity):
    """Sensor for total active numbers under the Play24 account."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:phone-multiple"

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_active_msisdns_count"
        self._attr_name = "Liczba aktywnych numerów"

    @property
    def native_value(self):
        return len(self.coordinator.data) if self.coordinator.data else 0


class Play24SuccessfulMsisdnsSensor(CoordinatorEntity, SensorEntity):
    """Sensor for count of successfully synchronized numbers (diagnostic)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:phone-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_successful_msisdns_count"
        self._attr_name = "Zsynchronizowane numery"

    @property
    def native_value(self):
        if hasattr(self.coordinator, "account_data"):
            return self.coordinator.account_data.get("successful_msisdns", len(self.coordinator.data or {}))
        return len(self.coordinator.data or {})


class Play24LastUpdateSensor(CoordinatorEntity, SensorEntity):
    """Sensor for last successful Play24 coordinator update timestamp."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-check-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_last_update"
        self._attr_name = "Ostatnia aktualizacja"

    @property
    def native_value(self):
        return self.coordinator.last_update_success_time


class Play24UnreadMessagesSensor(CoordinatorEntity, SensorEntity):
    """Sensor for unread Play24 inbox messages."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:email-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_unread_messages"
        self._attr_name = "Nieprzeczytane wiadomości"

    @property
    def native_value(self):
        if hasattr(self.coordinator, "account_data"):
            return self.coordinator.account_data.get("unread_messages", 0)
        return 0


class Play24AccountInvoiceAmountSensor(CoordinatorEntity, SensorEntity):
    """Sensor for aggregated account invoice amount."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:cash"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "PLN"

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_account_invoice_amount"
        self._attr_name = "Kwota ostatniej faktury konta"

    @property
    def native_value(self):
        return self.coordinator.account_data.get("invoice_amount_value")

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self.coordinator.account_data.get("invoice_number"):
            attrs["numer_faktury"] = self.coordinator.account_data.get("invoice_number")
        if self.coordinator.account_data.get("last_invoice_amount"):
            attrs["kwota_oryginalna"] = self.coordinator.account_data.get("last_invoice_amount")
        return attrs


class Play24AccountInvoiceDueDateSensor(CoordinatorEntity, SensorEntity):
    """Sensor for aggregated account invoice due date."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_account_invoice_due_date"
        self._attr_name = "Termin płatności faktury konta"

    @property
    def native_value(self):
        return self.coordinator.account_data.get("invoice_due_date")


class Play24AccountPaymentStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor for aggregated account invoice payment status."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:credit-card-check-outline"

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_account_payment_status"
        self._attr_name = "Status płatności faktury konta"

    @property
    def native_value(self):
        return self.coordinator.account_data.get("payment_status")


# =========================================================================
# PER-MSISDN SENSORS (CHILD DEVICES)
# =========================================================================

class Play24BaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Play24 MSISDN sensors."""
    
    _attr_has_entity_name = True
    
    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self.msisdn = msisdn


class Play24TariffSensor(Play24BaseSensor):
    _attr_icon = "mdi:tag-outline"

    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator, device_info, msisdn)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{msisdn}_tariff"
        self._attr_name = "Taryfa"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("tariff")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self.msisdn, {})
        tariff = data.get("tariff")
        attrs = {
            "typ_taryfy": _classify_tariff(tariff),
        }
        if data.get("offer_details"):
            attrs["szczegoly_oferty"] = data.get("offer_details")
        if data.get("group_owner_msisdn"):
            attrs["numer_glowny"] = data.get("group_owner_msisdn")
        if data.get("billing_cycle"):
            attrs["cykl_rozliczeniowy"] = data.get("billing_cycle")
        return attrs


class Play24ActiveComponentsSensor(Play24BaseSensor):
    _attr_icon = "mdi:format-list-checks"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator, device_info, msisdn)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{msisdn}_active_components"
        self._attr_name = "Aktywne usługi"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        components = data.get("active_components", [])
        return len(components)
        
    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return {
            "uslugi": data.get("active_components", [])
        }


class Play24BillingCycleSensor(Play24BaseSensor):
    _attr_icon = "mdi:calendar-sync"

    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator, device_info, msisdn)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{msisdn}_billing_cycle"
        self._attr_name = "Cykl rozliczeniowy"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("billing_cycle")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self.msisdn, {})
        attrs = {}
        if data.get("billing_cycle_day") is not None:
            attrs["dzien_cyklu"] = data.get("billing_cycle_day")
        return attrs


class Play24BillingCycleRemainingDaysSensor(Play24BaseSensor):
    _attr_icon = "mdi:calendar-clock"
    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator, device_info, msisdn)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{msisdn}_remaining_cycle_days"
        self._attr_name = "Pozostało dni cyklu"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("remaining_cycle_days")


class Play24DataLimitSensor(Play24BaseSensor):
    _attr_icon = "mdi:web"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = "GB"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator, device_info, msisdn)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{msisdn}_data_package"
        self._attr_name = "Pakiet danych"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("data_package_gb")


class Play24LastInvoiceAmountSensor(Play24BaseSensor):
    _attr_icon = "mdi:cash"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "PLN"

    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator, device_info, msisdn)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{msisdn}_last_invoice_amount"
        self._attr_name = "Kwota ostatniej faktury"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("invoice_amount_value")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self.msisdn, {})
        attrs = {}
        if data.get("invoice_number"):
            attrs["numer_faktury"] = data.get("invoice_number")
        if data.get("invoice_date"):
            attrs["data_wystawienia"] = data.get("invoice_date")
        if data.get("last_invoice_amount"):
            attrs["kwota_oryginalna"] = data.get("last_invoice_amount")
        return attrs


class Play24InvoiceDueDateSensor(Play24BaseSensor):
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator, device_info, msisdn)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{msisdn}_invoice_due_date"
        self._attr_name = "Termin płatności"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("invoice_due_date")


class Play24PaymentStatusSensor(Play24BaseSensor):
    _attr_icon = "mdi:credit-card-check-outline"

    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator, device_info, msisdn)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{msisdn}_payment_status"
        self._attr_name = "Status płatności"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("payment_status")


class Play24AccountBalanceSensor(Play24BaseSensor):
    _attr_icon = "mdi:cash"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "PLN"

    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator, device_info, msisdn)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{msisdn}_account_balance"
        self._attr_name = "Stan konta"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("account_balance")


class Play24AccountValiditySensor(Play24BaseSensor):
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator, device_info, msisdn)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{msisdn}_outgoing_validity"
        self._attr_name = "Ważność połączeń wychodzących"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("outgoing_validity") or data.get("account_validity")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self.msisdn, {})
        attrs = {}
        if data.get("account_validity"):
            attrs["waznosc_konta"] = data.get("account_validity")
        return attrs


class Play24DeviceSensor(Play24BaseSensor):
    """Deprecated separate sensor: device model is now stored in DeviceInfo.model."""
    _attr_icon = "mdi:cellphone"

    def __init__(self, coordinator, device_info: DeviceInfo, msisdn: str):
        super().__init__(coordinator, device_info, msisdn)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{msisdn}_device"
        self._attr_name = "Model telefonu"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("device")
