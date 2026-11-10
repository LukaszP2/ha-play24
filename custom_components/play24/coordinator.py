import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Play24AuthError, Play24Client, Play24ConnectionError, Play24DataError
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

FETCH_EXCEPTIONS = (
    Play24ConnectionError,
    Play24DataError,
    aiohttp.ClientError,
    TimeoutError,
    KeyError,
    ValueError,
    TypeError,
)


def _extract_data_package_gb(components: list[str]) -> float | None:
    if not components:
        return None
    total_gb = 0.0
    found = False
    for comp in components:
        m = re.search(r"([0-9]+(?:[\.,][0-9]+)?)\s*GB\b", str(comp), re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(",", "."))
                total_gb += val
                found = True
            except ValueError:
                pass
    return total_gb if found else None


class Play24DataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Play24 data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: Play24Client,
        entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize."""
        self.client = client
        self._lock = asyncio.Lock()
        self.last_update_success_time: datetime | None = None
        self.account_data: dict = {}
        self.config_entry = entry

        scan_interval = DEFAULT_SCAN_INTERVAL
        if entry and getattr(entry, "options", None):
            scan_interval_hours = entry.options.get(
                CONF_SCAN_INTERVAL_HOURS,
                entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS),
            )
            try:
                scan_interval = timedelta(hours=int(scan_interval_hours))
            except (ValueError, TypeError):
                scan_interval = DEFAULT_SCAN_INTERVAL

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
            config_entry=entry,
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            # 1. Pobierz wszystkie numery
            msisdns = await self.client.async_get_context_msisdns()

            # Fallback dla kont z 1 numerem lub gdy getContextMsisdns zwróci pustą listę
            if not msisdns:
                _LOGGER.warning(
                    "[DIAG] getContextMsisdns returned no numbers. Trying getOtherTile fallback..."
                )
                try:
                    other_tile = await self.client.async_get_other_tile()
                    raw_msisdn = other_tile.get("msisdn")
                    _LOGGER.debug(
                        "Single-number fallback result present=%s", bool(raw_msisdn)
                    )
                    if raw_msisdn:
                        clean_num = re.sub(r"\D", "", str(raw_msisdn))
                        if len(clean_num) >= 9:
                            fallback_num = clean_num[-9:]
                            msisdns = [fallback_num]
                            _LOGGER.debug("Recovered one account number from fallback")
                except Play24AuthError:
                    raise
                except FETCH_EXCEPTIONS as ex:
                    _LOGGER.warning(
                        "Could not resolve account numbers using fallback (%s)",
                        type(ex).__name__,
                    )

            if not msisdns:
                # An empty discovery response is not evidence that the account has no
                # numbers. Treat it as a failed refresh so HA retains the last good data.
                raise UpdateFailed("Play24 did not return any account numbers")

            account_messages = 0
            if hasattr(self.client, "async_get_messages"):
                try:
                    msg_res = await self.client.async_get_messages()
                    if isinstance(msg_res, dict):
                        account_messages = msg_res.get("unread_messages", 0)
                except Play24AuthError:
                    raise
                except FETCH_EXCEPTIONS as ex:
                    _LOGGER.debug("Could not fetch messages: %s", type(ex).__name__)

            data = {}
            # Sekwencyjne przełączanie kontekstu zamek (Lock)
            async with self._lock:
                for msisdn in msisdns:
                    try:
                        await self.client.async_change_account_context(msisdn)
                    except Play24AuthError:
                        raise
                    except FETCH_EXCEPTIONS as err:
                        # Never put a phone number or remote exception text in logs.
                        _LOGGER.warning(
                            "Could not switch account context for one number; skipping it (%s)",
                            type(err).__name__,
                        )
                        if self.data and msisdn in self.data:
                            data[msisdn] = self.data[msisdn]
                        continue

                    # Pobierz dane dla tego numeru świeżo po udanym przełączeniu
                    try:
                        other_tile = await self.client.async_get_other_tile()
                        if not isinstance(other_tile, dict):
                            other_tile = {}

                        active_components = []
                        if hasattr(self.client, "async_get_components_list"):
                            try:
                                comp_res = await self.client.async_get_components_list(
                                    "PLAY24_ACTIVE_COMPONENTS_SECTION"
                                )
                                if isinstance(comp_res, list):
                                    active_components = comp_res
                            except Play24AuthError:
                                raise
                            except FETCH_EXCEPTIONS as ex:
                                masked_num = (
                                    f"***{msisdn[-4:]}" if len(msisdn) >= 4 else "***"
                                )
                                _LOGGER.debug(
                                    "Could not fetch active components for %s: %s",
                                    masked_num,
                                    type(ex).__name__,
                                )

                        finance_tile = {}
                        if hasattr(self.client, "async_get_finance_tile"):
                            try:
                                fin_res = await self.client.async_get_finance_tile()
                                if isinstance(fin_res, dict):
                                    finance_tile = fin_res
                            except Play24AuthError:
                                raise
                            except FETCH_EXCEPTIONS as ex:
                                masked_num = (
                                    f"***{msisdn[-4:]}" if len(msisdn) >= 4 else "***"
                                )
                                _LOGGER.debug(
                                    "Could not fetch finance tile for %s: %s",
                                    masked_num,
                                    type(ex).__name__,
                                )

                        data[msisdn] = {
                            "msisdn": msisdn,
                            "device": other_tile.get("device"),
                            "tariff": other_tile.get("tariff"),
                            "billing_cycle": other_tile.get("billing_cycle"),
                            "billing_cycle_day": other_tile.get("billing_cycle_day"),
                            "remaining_cycle_days": other_tile.get(
                                "remaining_cycle_days"
                            ),
                            "offer_details": other_tile.get("offer_details"),
                            "group_owner_msisdn": other_tile.get("group_owner_msisdn"),
                            "active_components": active_components,
                            "data_package_gb": _extract_data_package_gb(
                                active_components
                            ),
                            "last_invoice_amount": finance_tile.get(
                                "last_invoice_amount"
                            ),
                            "invoice_amount_value": finance_tile.get(
                                "invoice_amount_value"
                            ),
                            "due_date": finance_tile.get("due_date"),
                            "invoice_due_date": finance_tile.get("invoice_due_date"),
                            "invoice_number": finance_tile.get("invoice_number"),
                            "invoice_date": finance_tile.get("invoice_date"),
                            "payment_status": finance_tile.get("payment_status"),
                            "account_balance": finance_tile.get("account_balance"),
                            "account_validity": finance_tile.get("account_validity"),
                            "outgoing_validity": finance_tile.get("outgoing_validity"),
                        }
                    except Play24AuthError:
                        raise
                    except FETCH_EXCEPTIONS as err:
                        _LOGGER.warning(
                            "Could not fetch data for one account number (%s)",
                            type(err).__name__,
                        )
                        if self.data and msisdn in self.data:
                            data[msisdn] = self.data[msisdn]
                        continue

            if not data:
                raise UpdateFailed(
                    "Play24 returned no usable data for any account number"
                )
            self.last_update_success_time = datetime.now(UTC)
            self.account_data = {
                "total_msisdns": len(msisdns),
                "successful_msisdns": len(data),
                "unread_messages": account_messages,
            }
            for mdata in data.values():
                if (
                    mdata.get("invoice_amount_value") is not None
                    or mdata.get("last_invoice_amount") is not None
                ):
                    self.account_data["invoice_amount_value"] = mdata.get(
                        "invoice_amount_value"
                    )
                    self.account_data["last_invoice_amount"] = mdata.get(
                        "last_invoice_amount"
                    )
                    self.account_data["invoice_due_date"] = mdata.get(
                        "invoice_due_date"
                    )
                    self.account_data["due_date"] = mdata.get("due_date")
                    self.account_data["payment_status"] = mdata.get("payment_status")
                    self.account_data["invoice_number"] = mdata.get("invoice_number")
                    break
            return data

        except Play24AuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except (Play24ConnectionError, Play24DataError) as err:
            raise UpdateFailed(f"Error communicating with Play24 API: {err}") from err
