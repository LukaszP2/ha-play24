import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

# Inject voluptuous mock if not installed
if "voluptuous" not in sys.modules:
    class MockVol(MagicMock):
        def Schema(self, *args, **kwargs):
            return MagicMock()
        def Required(self, *args, **kwargs):
            return MagicMock()
        def Optional(self, *args, **kwargs):
            return MagicMock()
        def In(self, *args, **kwargs):
            return MagicMock()
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

        def async_update_reload_and_abort(self, entry, data_updates=None, reason="reauth_successful", **kwargs):
            if entry and data_updates:
                entry.data.update(data_updates)
            return {"type": "abort", "reason": reason, **kwargs}

        async def async_set_unique_id(self, unique_id, **kwargs):
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            pass

    m_ce.ConfigFlow = DummyConfigFlow
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
        def __init__(self, hass=None, logger=None, name=None, update_interval=None, **kwargs):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.data = {}

        async def async_config_entry_first_refresh(self):
            pass

    class DummyCoordinatorEntity:
        def __init__(self, coordinator=None, *args, **kwargs):
            self.coordinator = coordinator

    class DummySensorEntity:
        _attr_has_entity_name = True
        _attr_icon = None
        _attr_unique_id = None
        _attr_name = None
        _attr_device_info = None
        _attr_device_class = None
        _attr_entity_category = None
        _attr_native_unit_of_measurement = None
        _attr_state_class = None

        @property
        def native_unit_of_measurement(self):
            return self._attr_native_unit_of_measurement

        @property
        def state_class(self):
            return self._attr_state_class

        @property
        def name(self):
            return self._attr_name

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

    class DummyEntityCategory:
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    m_const = MockModule()
    m_const.EntityCategory = DummyEntityCategory
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
        def __init__(self, domain="play24", title="Play24", data=None, unique_id=None, entry_id="test_entry_id"):
            self.domain = domain
            self.title = title
            self.data = dict(data) if data else {}
            self.unique_id = unique_id
            self.entry_id = entry_id

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

            hass.config_entries.async_entries = MagicMock(return_value=hass.config_entries._entries)
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

    hass_mock.config_entries.flow = FlowManager()

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

