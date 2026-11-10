import asyncio
import sys
from unittest.mock import MagicMock

import pytest

# Inject voluptuous mock if not installed
if "voluptuous" not in sys.modules:

    class MockMarker:
        def __init__(self, schema, default=None, **kwargs):
            self.schema = schema
            self._default = default

        def default(self):
            return self._default() if callable(self._default) else self._default

        def __str__(self):
            return str(self.schema)

        def __repr__(self):
            return f"Marker({self.schema!r})"

    class MockSchema:
        def __init__(self, schema=None, extra=None, **kwargs):
            self.schema = schema if isinstance(schema, dict) else {}
            self.extra = extra

        def __call__(self, val):
            return val

    class MockVol(MagicMock):
        ALLOW_EXTRA = "ALLOW_EXTRA"

        def Schema(self, *args, **kwargs):  # noqa: N802
            return MockSchema(*args, **kwargs)

        def Required(self, *args, **kwargs):  # noqa: N802
            return MockMarker(*args, **kwargs)

        def Optional(self, *args, **kwargs):  # noqa: N802
            return MockMarker(*args, **kwargs)

        def In(self, container):  # noqa: N802
            return lambda val: val

    sys.modules["voluptuous"] = MockVol()

# Inject lightweight mocks if homeassistant is not installed
if "homeassistant" not in sys.modules:

    class MockModule(MagicMock):
        @classmethod
        def __getattr__(cls, name):
            return MagicMock()

    ha_mock = MockModule()
    sys.modules["homeassistant"] = ha_mock
    sys.modules["homeassistant.core"] = MockModule()
    sys.modules["homeassistant.core"].callback = lambda func: func
    ha_mock.core = sys.modules["homeassistant.core"]

    # config_entries
    m_ce = MockModule()
    m_ce.SOURCE_USER = "user"
    m_ce.SOURCE_REAUTH = "reauth"
    m_ce.SOURCE_RECONFIGURE = "reconfigure"

    class DummyConfigFlow:
        def __init_subclass__(cls, domain=None, **kwargs):
            super().__init_subclass__()

        def __init__(self):
            self.hass = MagicMock()
            self.context = {}
            self.source = "user"

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

        def async_update_reload_and_abort(
            self, entry, data_updates=None, reason="reauth_successful", **kwargs
        ):
            if entry and data_updates:
                entry.data.update(data_updates)
            return {"type": "abort", "reason": reason, **kwargs}

        async def async_set_unique_id(self, unique_id, **kwargs):
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            pass

        def _abort_if_unique_id_mismatch(self, reason="wrong_account"):
            entry_id = self.context.get("entry_id")
            if (
                entry_id
                and hasattr(self, "hass")
                and hasattr(self.hass, "config_entries")
            ):
                entry = self.hass.config_entries.async_get_entry(entry_id)
                if (
                    entry
                    and getattr(entry, "unique_id", None)
                    and getattr(self, "unique_id", None)
                    and entry.unique_id != self.unique_id
                ):
                    raise Exception(f"Abort: {reason}")

    m_ce.ConfigFlow = DummyConfigFlow

    class DummyOptionsFlow:
        def __init__(self, config_entry=None):
            self._config_entry = config_entry
            self.hass = MagicMock()
            self.handler = (
                getattr(config_entry, "entry_id", None) if config_entry else None
            )

        @property
        def config_entry(self):
            if self._config_entry is not None:
                return self._config_entry
            if (
                hasattr(self, "handler")
                and hasattr(self, "hass")
                and hasattr(self.hass, "config_entries")
            ):
                entry = self.hass.config_entries.async_get_entry(self.handler)
                if entry is not None:
                    return entry
            return getattr(self, "_config_entry", None)

        @config_entry.setter
        def config_entry(self, value):
            self._config_entry = value

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

    m_ce.OptionsFlow = DummyOptionsFlow
    m_ce.ConfigFlowResult = dict
    sys.modules["homeassistant.config_entries"] = m_ce
    ha_mock.config_entries = m_ce

    m_helpers = MockModule()
    sys.modules["homeassistant.helpers"] = m_helpers
    ha_mock.helpers = m_helpers

    sys.modules["homeassistant.helpers.aiohttp_client"] = MockModule()
    m_helpers.aiohttp_client = sys.modules["homeassistant.helpers.aiohttp_client"]

    # update_coordinator
    class DummyCoordinator:
        def __init__(
            self, hass=None, logger=None, name=None, update_interval=None, **kwargs
        ):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = {}
            self._listeners = []

        async def async_config_entry_first_refresh(self):
            pass

        def async_add_listener(self, update_callback, context=None):
            self._listeners.append(update_callback)

            def remove_listener():
                if update_callback in self._listeners:
                    self._listeners.remove(update_callback)

            return remove_listener

        def async_update_listeners(self):
            for listener in list(self._listeners):
                listener()

    class DummyCoordinatorEntity:
        def __init__(self, coordinator=None, *args, **kwargs):
            self.coordinator = coordinator

    class DummySensorEntity:
        _attr_has_entity_name = True
        _attr_icon = None
        _attr_unique_id = None
        _attr_name = None
        _attr_translation_key = None
        _attr_device_info = None
        _attr_device_class = None
        _attr_entity_category = None
        _attr_native_unit_of_measurement = None
        _attr_state_class = None

        @property
        def translation_key(self):
            return self._attr_translation_key

        @property
        def native_unit_of_measurement(self):
            return self._attr_native_unit_of_measurement

        @property
        def state_class(self):
            return self._attr_state_class

        @property
        def name(self):
            if self._attr_name is not None:
                return self._attr_name
            translations = {
                "account_msisdns_count": "Liczba aktywnych numerów",
                "successful_msisdns_count": "Zsynchronizowane numery",
                "last_update": "Ostatnia aktualizacja",
                "unread_messages": "Nieprzeczytane wiadomości",
                "account_invoice_amount": "Kwota ostatniej faktury konta",
                "account_invoice_due_date": "Termin płatności faktury konta",
                "account_payment_status": "Status płatności faktury konta",
                "tariff": "Taryfa",
                "active_components": "Aktywne usługi",
                "billing_cycle": "Cykl rozliczeniowy",
                "remaining_cycle_days": "Pozostało dni cyklu",
                "data_package": "Pakiet danych",
                "last_invoice_amount": "Kwota ostatniej faktury",
                "invoice_due_date": "Termin płatności",
                "payment_status": "Status płatności",
                "account_balance": "Stan konta",
                "outgoing_validity": "Ważność połączeń wychodzących",
                "device": "Model telefonu",
            }
            return translations.get(
                self._attr_translation_key, self._attr_translation_key
            )

        @property
        def unique_id(self):
            return self._attr_unique_id

        @property
        def icon(self):
            return self._attr_icon

        @property
        def device_info(self):
            return self._attr_device_info

        @property
        def device_class(self):
            return self._attr_device_class

        @property
        def entity_category(self):
            return self._attr_entity_category

        @property
        def native_value(self):
            return None

        @property
        def extra_state_attributes(self):
            return {}

    m_uc = MockModule()
    m_uc.DataUpdateCoordinator = DummyCoordinator
    m_uc.CoordinatorEntity = DummyCoordinatorEntity

    class DummyUpdateFailed(Exception):
        pass

    m_uc.UpdateFailed = DummyUpdateFailed
    sys.modules["homeassistant.helpers.update_coordinator"] = m_uc
    m_helpers.update_coordinator = m_uc

    m_dr = MockModule()
    m_dr.DeviceInfo = dict
    sys.modules["homeassistant.helpers.device_registry"] = m_dr
    m_helpers.device_registry = m_dr

    sys.modules["homeassistant.helpers.entity_platform"] = MockModule()
    m_helpers.entity_platform = sys.modules["homeassistant.helpers.entity_platform"]

    sys.modules["homeassistant.helpers.entity_registry"] = MockModule()
    m_helpers.entity_registry = sys.modules["homeassistant.helpers.entity_registry"]

    m_comp = MockModule()
    sys.modules["homeassistant.components"] = m_comp
    ha_mock.components = m_comp

    class DummySensorDeviceClass:
        TIMESTAMP = "timestamp"
        MONETARY = "monetary"
        DATE = "date"
        DATA_SIZE = "data_size"

    class DummySensorStateClass:
        MEASUREMENT = "measurement"
        TOTAL = "total"
        TOTAL_INCREASING = "total_increasing"

    m_sensor = MockModule()
    m_sensor.SensorEntity = DummySensorEntity
    m_sensor.SensorDeviceClass = DummySensorDeviceClass
    m_sensor.SensorStateClass = DummySensorStateClass
    sys.modules["homeassistant.components.sensor"] = m_sensor
    m_comp.sensor = m_sensor

    def dummy_redact_data(data, to_redact):
        if not isinstance(data, dict):
            return data
        redacted = {}
        for k, v in data.items():
            if k in to_redact:
                redacted[k] = "**REDACTED**"
            elif isinstance(v, dict):
                redacted[k] = dummy_redact_data(v, to_redact)
            elif isinstance(v, list):
                redacted[k] = [
                    dummy_redact_data(item, to_redact)
                    if isinstance(item, dict)
                    else item
                    for item in v
                ]
            else:
                redacted[k] = v
        return redacted

    m_diag = MockModule()
    m_diag.async_redact_data = dummy_redact_data
    sys.modules["homeassistant.components.diagnostics"] = m_diag
    m_comp.diagnostics = m_diag

    class DummyEntityCategory:
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    try:
        from enum import StrEnum

        class DummyPlatform(StrEnum):
            SENSOR = "sensor"
    except ImportError:

        class DummyPlatform:
            SENSOR = "sensor"

    m_const = MockModule()
    m_const.EntityCategory = DummyEntityCategory
    m_const.Platform = DummyPlatform
    sys.modules["homeassistant.const"] = m_const
    ha_mock.const = m_const

    class DummyConfigEntryAuthFailed(Exception):
        pass

    class DummyConfigEntryNotReady(Exception):
        pass

    m_ex = MockModule()
    m_ex.ConfigEntryAuthFailed = DummyConfigEntryAuthFailed
    m_ex.ConfigEntryNotReady = DummyConfigEntryNotReady
    sys.modules["homeassistant.exceptions"] = m_ex
    ha_mock.exceptions = m_ex

    sys.modules["homeassistant.util"] = MockModule()
    ha_mock.util = sys.modules["homeassistant.util"]
    sys.modules["homeassistant.util.ssl"] = MockModule()

if "pytest_homeassistant_custom_component" not in sys.modules:
    m_ph = MagicMock()
    m_ph_common = MagicMock()

    class MockConfigEntry:
        def __init__(
            self,
            domain="play24",
            title="Play24",
            data=None,
            options=None,
            unique_id=None,
            entry_id="test_entry_id",
        ):
            self.domain = domain
            self.title = title
            self.data = dict(data) if data else {}
            self.options = dict(options) if options else {}
            self.unique_id = unique_id
            self.entry_id = entry_id
            self._update_listeners = []

        def add_update_listener(self, listener):
            self._update_listeners.append(listener)
            return listener

        def async_on_unload(self, listener):
            pass

        def add_to_hass(self, hass):
            if not hasattr(hass, "config_entries"):
                hass.config_entries = MagicMock()
            if not hasattr(hass.config_entries, "_entries"):
                hass.config_entries._entries = []
            hass.config_entries._entries.append(self)

            def get_entry(eid):
                for e in hass.config_entries._entries:
                    if e.entry_id == eid:
                        return e
                return self

            hass.config_entries.async_entries = MagicMock(
                return_value=hass.config_entries._entries
            )
            hass.config_entries.async_get_entry = MagicMock(side_effect=get_entry)

    m_ph_common.MockConfigEntry = MockConfigEntry
    sys.modules["pytest_homeassistant_custom_component"] = m_ph
    sys.modules["pytest_homeassistant_custom_component.common"] = m_ph_common


@pytest.fixture
def hass():
    from custom_components.play24.config_flow import Play24ConfigFlow

    hass_mock = MagicMock()
    hass_mock.data = {}
    hass_mock.config_entries = MagicMock()
    hass_mock.config_entries._entries = []

    flows = {}
    cur_step = {}

    class FlowManager:
        async def async_init(self, domain, context=None, data=None):
            flow = Play24ConfigFlow()
            flow.hass = hass_mock
            flow.context = dict(context or {})
            flow.source = flow.context.get("source", "user")
            flow_id = "test_flow_id"
            flows[flow_id] = flow
            if flow.source == "reauth":
                res = await flow.async_step_reauth(data)
            elif flow.source == "reconfigure":
                res = await flow.async_step_reconfigure(data)
            elif flow.source == "options":
                entry_id = flow.context.get("entry_id")
                entry = async_get_entry(entry_id)
                opt_flow = Play24ConfigFlow.async_get_options_flow(entry)
                opt_flow.hass = hass_mock
                opt_flow.handler = entry_id
                flows[flow_id] = opt_flow
                res = await opt_flow.async_step_init(data)
            else:
                res = await flow.async_step_user(data)
            if res.get("type") == "form":
                cur_step[flow_id] = res.get("step_id")
            res["flow_id"] = flow_id
            return res

        async def async_configure(self, flow_id, user_input=None):
            flow = flows[flow_id]
            step = cur_step.get(flow_id, "user")
            step_func = getattr(flow, f"async_step_{step}")
            res = await step_func(user_input)
            if res.get("type") == "form":
                cur_step[flow_id] = res.get("step_id")
            res["flow_id"] = flow_id
            return res

    class OptionsFlowManager:
        async def async_init(self, entry_id, context=None, data=None):
            entry = async_get_entry(entry_id)
            flow = Play24ConfigFlow.async_get_options_flow(entry)
            flow.hass = hass_mock
            flow.handler = entry_id
            flow_id = f"options_flow_{entry_id}"
            flows[flow_id] = flow
            res = await flow.async_step_init(data)
            if res.get("type") == "form":
                cur_step[flow_id] = res.get("step_id")
            res["flow_id"] = flow_id
            return res

        async def async_configure(self, flow_id, user_input=None):
            flow = flows[flow_id]
            step = cur_step.get(flow_id, "init")
            step_func = getattr(flow, f"async_step_{step}")
            res = await step_func(user_input)
            if res.get("type") == "form":
                cur_step[flow_id] = res.get("step_id")
            elif res.get("type") == "create_entry":
                entry = getattr(flow, "config_entry", None)
                if entry:
                    entry.options.update(res.get("data", {}))
                    for listener in getattr(entry, "_update_listeners", []):
                        val = listener(hass_mock, entry)
                        if asyncio.iscoroutine(val):
                            await val
            res["flow_id"] = flow_id
            return res

    hass_mock.config_entries.flow = FlowManager()
    hass_mock.config_entries.options = OptionsFlowManager()

    def async_entries(domain=None):
        return hass_mock.config_entries._entries

    hass_mock.config_entries.async_entries = MagicMock(side_effect=async_entries)

    def async_get_entry(entry_id):
        for e in hass_mock.config_entries._entries:
            if e.entry_id == entry_id:
                return e
        return None

    hass_mock.config_entries.async_get_entry = MagicMock(side_effect=async_get_entry)

    return hass_mock
