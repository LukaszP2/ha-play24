import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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


def _create_msisdn_sensors(
    coordinator: Any,
    entry_id: str,
    msisdn: str,
    msisdn_data: dict[str, Any],
) -> list[SensorEntity]:
    """Create child sensor entities for a specific MSISDN."""
    device_info = DeviceInfo(
        identifiers={(DOMAIN, msisdn)},
        name=f"Play24 {msisdn}",
        manufacturer="Play",
        model=msisdn_data.get("device") or "Play24 Device",
        via_device=(DOMAIN, entry_id),
    )

    sensors: list[SensorEntity] = [
        Play24TariffSensor(coordinator, device_info, msisdn, entry_id),
        Play24ActiveComponentsSensor(coordinator, device_info, msisdn, entry_id),
        Play24BillingCycleSensor(coordinator, device_info, msisdn, entry_id),
    ]

    # Remaining cycle days
    tariff_type = _classify_tariff(msisdn_data.get("tariff"))
    if (
        msisdn_data.get("remaining_cycle_days") is not None
        or msisdn_data.get("billing_cycle") is not None
        or tariff_type == "postpaid"
    ):
        sensors.append(
            Play24BillingCycleRemainingDaysSensor(
                coordinator, device_info, msisdn, entry_id
            )
        )

    # Data package limit sensor
    if msisdn_data.get("data_package_gb") is not None:
        sensors.append(
            Play24DataLimitSensor(coordinator, device_info, msisdn, entry_id)
        )

    # Postpaid sensors
    if (
        tariff_type == "postpaid"
        or msisdn_data.get("invoice_amount_value") is not None
        or msisdn_data.get("invoice_due_date") is not None
    ):
        sensors.append(
            Play24LastInvoiceAmountSensor(coordinator, device_info, msisdn, entry_id)
        )
        sensors.append(
            Play24InvoiceDueDateSensor(coordinator, device_info, msisdn, entry_id)
        )
        sensors.append(
            Play24PaymentStatusSensor(coordinator, device_info, msisdn, entry_id)
        )

    # Prepaid sensors
    if (
        tariff_type == "prepaid"
        or msisdn_data.get("account_balance") is not None
        or msisdn_data.get("outgoing_validity") is not None
    ):
        sensors.append(
            Play24AccountBalanceSensor(coordinator, device_info, msisdn, entry_id)
        )
        sensors.append(
            Play24AccountValiditySensor(coordinator, device_info, msisdn, entry_id)
        )

    return sensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Play24 sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Parent Account Device Info
    parent_device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Konto Play24",
        manufacturer="Play",
        model="Play24 Account",
        configuration_url="https://24.play.pl",
    )

    sensors: list[SensorEntity] = [
        Play24AccountMsisdnsSensor(coordinator, parent_device_info, entry.entry_id),
        Play24SuccessfulMsisdnsSensor(coordinator, parent_device_info, entry.entry_id),
        Play24LastUpdateSensor(coordinator, parent_device_info, entry.entry_id),
        Play24UnreadMessagesSensor(coordinator, parent_device_info, entry.entry_id),
    ]

    account_data = (
        coordinator.account_data
        if (
            hasattr(coordinator, "account_data")
            and isinstance(coordinator.account_data, dict)
        )
        else {}
    )

    account_invoice_sensors_added = False
    # Account-level invoice sensors if invoice data is available
    if (
        account_data.get("invoice_amount_value") is not None
        or account_data.get("last_invoice_amount") is not None
    ):
        sensors.append(
            Play24AccountInvoiceAmountSensor(
                coordinator, parent_device_info, entry.entry_id
            )
        )
        sensors.append(
            Play24AccountInvoiceDueDateSensor(
                coordinator, parent_device_info, entry.entry_id
            )
        )
        sensors.append(
            Play24AccountPaymentStatusSensor(
                coordinator, parent_device_info, entry.entry_id
            )
        )
        account_invoice_sensors_added = True

    known_msisdns: set[str] = set()

    if coordinator.data and isinstance(coordinator.data, dict):
        for msisdn, msisdn_data in coordinator.data.items():
            known_msisdns.add(msisdn)
            sensors.extend(
                _create_msisdn_sensors(
                    coordinator,
                    entry.entry_id,
                    msisdn,
                    msisdn_data if isinstance(msisdn_data, dict) else {},
                )
            )

    async_add_entities(sensors)

    @callback
    def _async_check_new_entities() -> None:
        """Dynamically detect and register new MSISDNs upon coordinator update."""
        nonlocal account_invoice_sensors_added

        new_sensors: list[SensorEntity] = []

        if not account_invoice_sensors_added:
            acc_data = getattr(coordinator, "account_data", {}) or {}
            if (
                acc_data.get("invoice_amount_value") is not None
                or acc_data.get("last_invoice_amount") is not None
            ):
                new_sensors.append(
                    Play24AccountInvoiceAmountSensor(
                        coordinator, parent_device_info, entry.entry_id
                    )
                )
                new_sensors.append(
                    Play24AccountInvoiceDueDateSensor(
                        coordinator, parent_device_info, entry.entry_id
                    )
                )
                new_sensors.append(
                    Play24AccountPaymentStatusSensor(
                        coordinator, parent_device_info, entry.entry_id
                    )
                )
                account_invoice_sensors_added = True

        if coordinator.data and isinstance(coordinator.data, dict):
            for msisdn, msisdn_data in coordinator.data.items():
                if msisdn not in known_msisdns:
                    known_msisdns.add(msisdn)
                    new_sensors.extend(
                        _create_msisdn_sensors(
                            coordinator,
                            entry.entry_id,
                            msisdn,
                            msisdn_data if isinstance(msisdn_data, dict) else {},
                        )
                    )

        if new_sensors:
            _LOGGER.debug(
                "Dynamic discovery added %d new sensor entities",
                len(new_sensors),
            )
            async_add_entities(new_sensors)

    remove_listener = coordinator.async_add_listener(_async_check_new_entities)
    if hasattr(entry, "async_on_unload"):
        entry.async_on_unload(remove_listener)


# =========================================================================
# ACCOUNT-LEVEL SENSORS (PARENT DEVICE)
# =========================================================================


class Play24AccountMsisdnsSensor(CoordinatorEntity, SensorEntity):
    """Sensor for total active numbers under the Play24 account."""

    _attr_has_entity_name = True
    _attr_translation_key = "account_msisdns_count"
    _attr_icon = "mdi:phone-multiple"

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_active_msisdns_count"

    @property
    def native_value(self):
        return len(self.coordinator.data) if self.coordinator.data else 0


class Play24SuccessfulMsisdnsSensor(CoordinatorEntity, SensorEntity):
    """Sensor for count of successfully synchronized numbers (diagnostic)."""

    _attr_has_entity_name = True
    _attr_translation_key = "successful_msisdns_count"
    _attr_icon = "mdi:phone-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_successful_msisdns_count"

    @property
    def native_value(self):
        if hasattr(self.coordinator, "account_data"):
            return self.coordinator.account_data.get(
                "successful_msisdns", len(self.coordinator.data or {})
            )
        return len(self.coordinator.data or {})


class Play24LastUpdateSensor(CoordinatorEntity, SensorEntity):
    """Sensor for last successful Play24 coordinator update timestamp."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_update"
    _attr_icon = "mdi:clock-check-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_last_update"

    @property
    def native_value(self):
        return self.coordinator.last_update_success_time


class Play24UnreadMessagesSensor(CoordinatorEntity, SensorEntity):
    """Sensor for unread Play24 inbox messages."""

    _attr_has_entity_name = True
    _attr_translation_key = "unread_messages"
    _attr_icon = "mdi:email-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_unread_messages"

    @property
    def native_value(self):
        if hasattr(self.coordinator, "account_data"):
            return self.coordinator.account_data.get("unread_messages", 0)
        return 0


class Play24AccountInvoiceAmountSensor(CoordinatorEntity, SensorEntity):
    """Sensor for aggregated account invoice amount."""

    _attr_has_entity_name = True
    _attr_translation_key = "account_invoice_amount"
    _attr_icon = "mdi:cash"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "PLN"

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_account_invoice_amount"

    @property
    def native_value(self):
        return self.coordinator.account_data.get("invoice_amount_value")

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self.coordinator.account_data.get("invoice_number"):
            attrs["numer_faktury"] = self.coordinator.account_data.get("invoice_number")
        if self.coordinator.account_data.get("last_invoice_amount"):
            attrs["kwota_oryginalna"] = self.coordinator.account_data.get(
                "last_invoice_amount"
            )
        return attrs


class Play24AccountInvoiceDueDateSensor(CoordinatorEntity, SensorEntity):
    """Sensor for aggregated account invoice due date."""

    _attr_has_entity_name = True
    _attr_translation_key = "account_invoice_due_date"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_account_invoice_due_date"

    @property
    def native_value(self):
        return self.coordinator.account_data.get("invoice_due_date")


class Play24AccountPaymentStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor for aggregated account invoice payment status."""

    _attr_has_entity_name = True
    _attr_translation_key = "account_payment_status"
    _attr_icon = "mdi:credit-card-check-outline"

    def __init__(self, coordinator, device_info: DeviceInfo, entry_id: str):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry_id}_account_payment_status"

    @property
    def native_value(self):
        return self.coordinator.account_data.get("payment_status")


# =========================================================================
# PER-MSISDN SENSORS (CHILD DEVICES)
# =========================================================================


class Play24BaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Play24 MSISDN sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        device_info: DeviceInfo,
        msisdn: str,
        entry_id: str | None = None,
    ):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self.msisdn = msisdn
        coord_entry_id = getattr(
            getattr(coordinator, "config_entry", None), "entry_id", None
        )
        self.entry_id = entry_id or coord_entry_id or "play24"


class Play24TariffSensor(Play24BaseSensor):
    _attr_translation_key = "tariff"
    _attr_icon = "mdi:tag-outline"

    def __init__(
        self,
        coordinator,
        device_info: DeviceInfo,
        msisdn: str,
        entry_id: str | None = None,
    ):
        super().__init__(coordinator, device_info, msisdn, entry_id)
        self._attr_unique_id = f"{self.entry_id}_{msisdn}_tariff"

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
    _attr_translation_key = "active_components"
    _attr_icon = "mdi:format-list-checks"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        device_info: DeviceInfo,
        msisdn: str,
        entry_id: str | None = None,
    ):
        super().__init__(coordinator, device_info, msisdn, entry_id)
        self._attr_unique_id = f"{self.entry_id}_{msisdn}_active_components"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        components = data.get("active_components", [])
        return len(components)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return {"uslugi": data.get("active_components", [])}


class Play24BillingCycleSensor(Play24BaseSensor):
    _attr_translation_key = "billing_cycle"
    _attr_icon = "mdi:calendar-sync"

    def __init__(
        self,
        coordinator,
        device_info: DeviceInfo,
        msisdn: str,
        entry_id: str | None = None,
    ):
        super().__init__(coordinator, device_info, msisdn, entry_id)
        self._attr_unique_id = f"{self.entry_id}_{msisdn}_billing_cycle"

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
    _attr_translation_key = "remaining_cycle_days"
    _attr_icon = "mdi:calendar-clock"
    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        device_info: DeviceInfo,
        msisdn: str,
        entry_id: str | None = None,
    ):
        super().__init__(coordinator, device_info, msisdn, entry_id)
        self._attr_unique_id = f"{self.entry_id}_{msisdn}_remaining_cycle_days"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("remaining_cycle_days")


class Play24DataLimitSensor(Play24BaseSensor):
    _attr_translation_key = "data_package"
    _attr_icon = "mdi:web"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = "GB"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        device_info: DeviceInfo,
        msisdn: str,
        entry_id: str | None = None,
    ):
        super().__init__(coordinator, device_info, msisdn, entry_id)
        self._attr_unique_id = f"{self.entry_id}_{msisdn}_data_package"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("data_package_gb")


class Play24LastInvoiceAmountSensor(Play24BaseSensor):
    _attr_translation_key = "last_invoice_amount"
    _attr_icon = "mdi:cash"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "PLN"

    def __init__(
        self,
        coordinator,
        device_info: DeviceInfo,
        msisdn: str,
        entry_id: str | None = None,
    ):
        super().__init__(coordinator, device_info, msisdn, entry_id)
        self._attr_unique_id = f"{self.entry_id}_{msisdn}_last_invoice_amount"

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
    _attr_translation_key = "invoice_due_date"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(
        self,
        coordinator,
        device_info: DeviceInfo,
        msisdn: str,
        entry_id: str | None = None,
    ):
        super().__init__(coordinator, device_info, msisdn, entry_id)
        self._attr_unique_id = f"{self.entry_id}_{msisdn}_invoice_due_date"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("invoice_due_date")


class Play24PaymentStatusSensor(Play24BaseSensor):
    _attr_translation_key = "payment_status"
    _attr_icon = "mdi:credit-card-check-outline"

    def __init__(
        self,
        coordinator,
        device_info: DeviceInfo,
        msisdn: str,
        entry_id: str | None = None,
    ):
        super().__init__(coordinator, device_info, msisdn, entry_id)
        self._attr_unique_id = f"{self.entry_id}_{msisdn}_payment_status"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("payment_status")


class Play24AccountBalanceSensor(Play24BaseSensor):
    _attr_translation_key = "account_balance"
    _attr_icon = "mdi:cash"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "PLN"

    def __init__(
        self,
        coordinator,
        device_info: DeviceInfo,
        msisdn: str,
        entry_id: str | None = None,
    ):
        super().__init__(coordinator, device_info, msisdn, entry_id)
        self._attr_unique_id = f"{self.entry_id}_{msisdn}_account_balance"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.msisdn, {})
        return data.get("account_balance")


class Play24AccountValiditySensor(Play24BaseSensor):
    _attr_translation_key = "outgoing_validity"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(
        self,
        coordinator,
        device_info: DeviceInfo,
        msisdn: str,
        entry_id: str | None = None,
    ):
        super().__init__(coordinator, device_info, msisdn, entry_id)
        self._attr_unique_id = f"{self.entry_id}_{msisdn}_outgoing_validity"

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
