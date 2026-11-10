"""Diagnostics support for Play24."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_JSESSIONID, DOMAIN
from .coordinator import Play24DataUpdateCoordinator

TO_REDACT = {
    CONF_JSESSIONID,
    "msisdn",
    "group_owner_msisdn",
    "invoice_number",
}


def _mask_msisdn(msisdn: str) -> str:
    """Mask phone number keeping only last 4 digits."""
    clean = str(msisdn).strip()
    return f"***{clean[-4:]}" if len(clean) >= 4 else "***"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: Play24DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    sanitized_data = {}
    if coordinator.data:
        for msisdn, mdata in coordinator.data.items():
            masked_key = _mask_msisdn(msisdn)
            sanitized_item = dict(mdata)
            if "msisdn" in sanitized_item:
                sanitized_item["msisdn"] = masked_key
            if sanitized_item.get("group_owner_msisdn"):
                sanitized_item["group_owner_msisdn"] = _mask_msisdn(
                    sanitized_item["group_owner_msisdn"]
                )
            sanitized_data[masked_key] = sanitized_item

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "account_data": async_redact_data(dict(coordinator.account_data), TO_REDACT),
        "data": sanitized_data,
    }
