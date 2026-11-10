import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Play24AuthError, Play24Client, Play24ConnectionError
from .const import (
    CONF_DWRSESSIONID,
    CONF_JSESSIONID,
    CONF_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
)
from .coordinator import Play24DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Play24 from a config entry."""
    jsessionid = entry.data[CONF_JSESSIONID]
    dwrsessionid = entry.data.get(CONF_DWRSESSIONID)
    session = async_get_clientsession(hass)

    client = Play24Client(jsessionid, session, dwrsessionid=dwrsessionid)

    try:
        await client.async_test_connection()
    except Play24AuthError as err:
        raise ConfigEntryAuthFailed(err) from err
    except Play24ConnectionError as err:
        raise ConfigEntryNotReady(err) from err

    coordinator = Play24DataUpdateCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update coordinator update_interval when options are updated."""
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        scan_interval_hours = entry.options.get(
            CONF_SCAN_INTERVAL_HOURS,
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS),
        )
        try:
            coordinator.update_interval = timedelta(hours=int(scan_interval_hours))
        except (ValueError, TypeError):
            coordinator.update_interval = DEFAULT_SCAN_INTERVAL
        _LOGGER.debug(
            "Updated coordinator update_interval to %s for entry %s",
            coordinator.update_interval,
            entry.entry_id,
        )


async_update_options = update_listener


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
