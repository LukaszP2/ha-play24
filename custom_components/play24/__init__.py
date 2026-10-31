import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_JSESSIONID
from .api import Play24Client, Play24AuthError, Play24ConnectionError, Play24DataError
from .coordinator import Play24DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Play24 from a config entry."""
    jsessionid = entry.data[CONF_JSESSIONID]
    session = async_get_clientsession(hass)
    
    client = Play24Client(jsessionid, session)
    
    try:
        await client.async_test_connection()
    except Play24AuthError as err:
        raise ConfigEntryAuthFailed(err) from err
    except Play24ConnectionError as err:
        raise ConfigEntryNotReady(err) from err

    coordinator = Play24DataUpdateCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
