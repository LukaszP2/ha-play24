import re
import logging
import random
import string
from typing import Any, Dict
import aiohttp
import asyncio

_LOGGER = logging.getLogger(__name__)

def _decode_js_string(value: str) -> str:
    """Decode common JavaScript string escapes without corrupting Unicode text."""
    replacements = {
        "n": "\n", "r": "\r", "t": "\t", "b": "\b",
        "f": "\f", "v": "\v", "0": "\0", "\\": "\\",
        '"': '"', "'": "'", "/": "/",
    }

    def replace_escape(match: re.Match[str]) -> str:
        escape = match.group(1)
        if escape.startswith("u") and len(escape) == 5:
            return chr(int(escape[1:], 16))
        if escape.startswith("x") and len(escape) == 3:
            return chr(int(escape[1:], 16))
        return replacements.get(escape, escape)

    return re.sub(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)", replace_escape, value)


def _parse_currency_amount(val: str | None) -> float | None:
    if not val:
        return None
    m = re.search(r'([0-9]+(?:[\.,][0-9]{1,2})?)', str(val))
    if m:
        cleaned = m.group(1).replace(',', '.')
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _parse_polish_date(val: str | None) -> str | None:
    if not val:
        return None
    m = re.search(r'(\d{2})[\.\-](\d{2})[\.\-](\d{4})', str(val))
    if m:
        day, month, year = m.groups()
        return f"{year}-{month}-{day}"
    return None


class Play24AuthError(Exception):
    pass

class Play24ConnectionError(Exception):
    pass

class Play24DataError(Exception):
    pass

class Play24Client:
    def __init__(self, jsessionid: str, session: aiohttp.ClientSession):
        self._session = session
        self._jsessionid = jsessionid
        self._csrf_token = None
        self._batch_id = 0
        
        self._dwrsess = "FIPNQ!k4teb4g7FlmjZELiiEHj2uQoSuo5q"
        rand_page = "".join(random.choices(string.ascii_letters + string.digits, k=16))
        self._page_id = f"{rand_page}-0"
        self._script_session_id = f"{self._dwrsess}/{self._page_id}"
        
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Origin": "https://24.play.pl",
            "Referer": "https://24.play.pl/Play24/Welcome",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
        }
        
        # We manually pass cookies in requests to avoid polluting shared ClientSession cookie_jar
        self._cookies = {
            "JSESSIONID": self._jsessionid,
            "DWRSESSIONID": self._dwrsess
        }

    async def async_test_connection(self) -> bool:
        """Verifies session validity."""
        try:
            async with self._session.get(
                "https://24.play.pl/Play24/Welcome",
                headers=self._headers,
                cookies=self._cookies,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return True
                raise Play24AuthError(f"Session expired or invalid (HTTP {resp.status})")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise Play24ConnectionError(f"Cannot connect to Play24: {e}")

    async def async_get_csrf(self):
        """Fetches the P24_CSRFTOKEN required for DWR requests."""
        headers = dict(self._headers)
        headers["FETCH-CSRF-TOKEN"] = "1"
        try:
            async with self._session.post(
                "https://24.play.pl/Play24/CsrfJavaScriptServlet",
                headers=headers,
                cookies=self._cookies,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    raise Play24DataError(f"Failed to fetch CSRF. Status: {resp.status}")
                text = await resp.text()
                if "P24_CSRFTOKEN:" in text:
                    _, _, token = text.partition(":")
                    self._csrf_token = token.strip()
                    if self._csrf_token:
                        return self._csrf_token
                raise Play24DataError("CSRF token not found in response")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise Play24ConnectionError(f"Network error while fetching CSRF: {e}")

    async def _async_dwr_request(self, script_name: str, method_name: str, extra_params: list = None) -> str:
        if not self._csrf_token:
            await self.async_get_csrf()

        url = f"https://24.play.pl/Play24/dwr/call/plaincall/{script_name}.{method_name}.dwr"
        
        payload_parts = [
            "callCount=1",
            "nextReverseAjaxIndex=0",
            f"c0-scriptName={script_name}",
            f"c0-methodName={method_name}",
            "c0-id=0",
        ]
        
        if extra_params:
            for i, p in enumerate(extra_params):
                payload_parts.append(f"c0-param{i}={p}")
                
        payload_parts.extend([
            f"batchId={self._batch_id}",
            "instanceId=0",
            "page=%2FPlay24%2FWelcome",
            f"scriptSessionId={self._script_session_id}",
            ""
        ])
        
        payload = "\n".join(payload_parts)
        self._batch_id += 1

        headers = dict(self._headers)
        headers["Content-Type"] = "text/plain"
        headers["P24_CSRFTOKEN"] = self._csrf_token

        try:
            async with self._session.post(
                url, data=payload, headers=headers, cookies=self._cookies,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    _LOGGER.debug("DWR %s.%s HTTP %s response_length=%s", script_name, method_name, resp.status, len(text))
                    if 'java.lang.SecurityException' in text:
                        if 'CSRF Security Error' in text:
                            raise Play24AuthError("CSRF Security Error (session invalidated or CSRF mismatch)")
                        # The response can contain account identifiers or session data.
                        raise Play24DataError("DWR security exception returned by Play24")
                    return text
                if resp.status in [401, 403]:
                    raise Play24AuthError(f"Authentication error in DWR (HTTP {resp.status})")
                raise Play24DataError(f"DWR request failed: HTTP {resp.status}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise Play24ConnectionError(f"Network error in DWR request: {e}")

    def _parse_dwr_html(self, text: str) -> str:
        html_parts = []
        # Captures double-quoted strings for view, html, content, and account view properties
        # Handles escaped quotes (\" or \\") and characters without prematurely ending on commas
        pattern = r'(?:view|content|html|myAccountPhoneView|myAccountTariffView|myAccountNumberView)\s*[:=]\s*"((?:[^"\\]|\\.)*)"'
        for match in re.finditer(pattern, text, re.DOTALL):
            raw = _decode_js_string(match.group(1))
            raw = raw.replace('\\r', '').replace('\\n', '').replace('\\"', '"').replace('\\/', '/').replace('&quot;', '"').replace('&amp;', '&')
            html_parts.append(raw)
        return "".join(html_parts)

    async def async_get_other_tile(self) -> Dict[str, Any]:
        text = await self._async_dwr_request("myAccountRemoteService", "getOtherTile")
        html = self._parse_dwr_html(text)
        
        device_match = re.search(r'<div class="pointOut">(.*?)</div>', html)
        tariff_match = re.search(r'<h2>Moja oferta</h2>.*?<div class="pointOut">(.*?)</div>', html, re.DOTALL)
        msisdn_match = re.search(r'<div class="pointOut number">(.*?)</div>', html)
        
        cycle_match = re.search(r'(?:Okres rozliczeniowy od|Pocz\u0105tek cyklu[^<]*:)\s*([0-9]+\.\s*dzie\u0144\s*miesi\u0105ca)', html, re.IGNORECASE)
        if not cycle_match:
            cycle_match = re.search(r'([0-9]+\.\s*dzie\u0144\s*miesi\u0105ca)', html, re.IGNORECASE)
            
        cycle_day = None
        if cycle_match:
            day_m = re.search(r'(\d+)', cycle_match.group(1))
            if day_m:
                cycle_day = int(day_m.group(1))

        rem_days_match = re.search(r'Pozosta\u0142o\s+([0-9]+)\s+dni', html, re.IGNORECASE)
        remaining_cycle_days = int(rem_days_match.group(1)) if rem_days_match else None

        offer_m = re.search(r'id=["\']postpaidGroupsButtonSection["\'][^>]*>.*?<span>(.*?)</span>', html, re.DOTALL | re.IGNORECASE)
        offer_details = re.sub(r'<[^>]+>', '', offer_m.group(1)).strip() if offer_m else None

        owner_m = re.search(r'class=["\']owner-msisdn["\']>(.*?)</span>', html, re.IGNORECASE)
        group_owner_msisdn = re.sub(r'\D', '', owner_m.group(1)) if owner_m else None
        if group_owner_msisdn and len(group_owner_msisdn) >= 9:
            group_owner_msisdn = group_owner_msisdn[-9:]
        
        msisdn = msisdn_match.group(1).strip() if msisdn_match else None
        
        result = {
            "device": device_match.group(1).strip() if device_match else None,
            "tariff": tariff_match.group(1).strip() if tariff_match else None,
            "billing_cycle": cycle_match.group(1).strip() if cycle_match else None,
            "billing_cycle_day": cycle_day,
            "remaining_cycle_days": remaining_cycle_days,
            "offer_details": offer_details,
            "group_owner_msisdn": group_owner_msisdn,
            "msisdn": msisdn
        }
        _LOGGER.debug("Parsed Play24 account tile (device=%s, tariff=%s, billing_cycle=%s)", bool(result["device"]), bool(result["tariff"]), bool(result["billing_cycle"]))
        return result

    async def async_get_finance_tile(self) -> Dict[str, Any]:
        text = await self._async_dwr_request("myAccountRemoteService", "getFinanceTile")
        html = self._parse_dwr_html(text)
        
        invoice_amount_match = re.search(r'<div[^>]*\blastInvoiceAmount\b[^>]*>(.*?)</div>', html, re.IGNORECASE)
        if not invoice_amount_match:
            invoice_amount_match = re.search(r'<div[^>]*class=["\'][^"\']*pointOut[^"\']*["\'][^>]*>(.*?)</div>', html, re.IGNORECASE)
        
        due_date_match = re.search(r'Termin\s+p\u0142atno\u015Bci\s*:\s*([0-9\.\-]+)', html, re.IGNORECASE)
        doc_num_match = re.search(r'Numer\s+dokumentu\s*:\s*([^\s<]+)', html, re.IGNORECASE)
        doc_date_match = re.search(r'Ostatni\s+dokument\s*\(([0-9\.\-]+)\)', html, re.IGNORECASE)
        status_match = re.search(r'(Dokument\s+(?:nie)?op\u0142acony|Op\u0142acony|Nieop\u0142acony)', html, re.IGNORECASE)
        balance_match = re.search(r'Stan\s+konta\s*:\s*([0-9\s,.]+)', html, re.IGNORECASE)
        validity_match = re.search(r'Wa\u017Cno\u015B\u0107\s+(?:po\u0142\u0105cze\u0144\s+wychodz\u0105cych|konta)\s*:\s*([0-9\.\-]+)', html, re.IGNORECASE)
        outgoing_val_match = re.search(r'Wa\u017Cno\u015B\u0107\s+po\u0142\u0105cze\u0144\s+wychodz\u0105cych\s*:\s*([0-9\.\-]+)', html, re.IGNORECASE)

        raw_invoice = invoice_amount_match.group(1).strip() if invoice_amount_match else None
        invoice_text = None
        invoice_value = None
        account_balance = None

        if raw_invoice:
            clean_str = re.sub(r'<[^>]+>', '', raw_invoice).strip()
            if "lastInvoiceAmount" in (invoice_amount_match.group(0) if invoice_amount_match else ""):
                invoice_text = clean_str
                invoice_value = _parse_currency_amount(clean_str)
            elif balance_match:
                account_balance = _parse_currency_amount(balance_match.group(1))
            else:
                val = _parse_currency_amount(clean_str)
                if due_date_match:
                    invoice_text = clean_str
                    invoice_value = val
                else:
                    account_balance = val

        due_date_raw = due_date_match.group(1).strip() if due_date_match else None
        doc_date_raw = doc_date_match.group(1).strip() if doc_date_match else None
        validity_raw = validity_match.group(1).strip() if validity_match else None
        outgoing_val_raw = outgoing_val_match.group(1).strip() if outgoing_val_match else None

        return {
            "last_invoice_amount": invoice_text,
            "invoice_amount_value": invoice_value,
            "due_date": due_date_raw,
            "invoice_due_date": _parse_polish_date(due_date_raw),
            "invoice_number": doc_num_match.group(1).strip() if doc_num_match else None,
            "invoice_date": _parse_polish_date(doc_date_raw),
            "payment_status": status_match.group(1).strip() if status_match else None,
            "account_balance": account_balance,
            "account_validity": _parse_polish_date(validity_raw),
            "outgoing_validity": _parse_polish_date(outgoing_val_raw),
        }

    async def async_get_messages(self) -> Dict[str, Any]:
        text = await self._async_dwr_request("messageRemoteService", "getMessages")
        html = self._parse_dwr_html(text)
        # Extract number of unread messages if possible, else just store html len
        count_match = re.search(r'Masz\s+<span[^>]*>([0-9]+)</span>\s+nieprzeczytane', html)
        unread = int(count_match.group(1)) if count_match else 0
        return {"unread_messages": unread, "raw_html_len": len(html)}

    async def async_get_context_msisdns(self) -> list[str]:
        text = await self._async_dwr_request("accountContextChangeService", "getContextMsisdns")
        msisdns = []
        html = self._parse_dwr_html(text)

        _LOGGER.debug("Parsed account context response (response_length=%s, html_length=%s)", len(text), len(html))

        # Layer 1: Struktura HTML podzielona na kontenery (li, tr, div)
        if html:
            if '<li' in html.lower():
                items = re.split(r'<li\b', html, flags=re.IGNORECASE)[1:]
            elif '<tr' in html.lower():
                items = re.split(r'<tr\b', html, flags=re.IGNORECASE)[1:]
            elif '<div' in html.lower():
                items = re.split(r'<div\b', html, flags=re.IGNORECASE)[1:]
            else:
                items = [html]

            for item in items:
                # 1A: <input ... class="msisdn" ... value="..."/> w dowolnej kolejności atrybutów
                input_matches = re.findall(r'<input[^>]*\bclass=["\'][^"\']*\bmsisdn\b[^"\']*["\'][^>]*\bvalue=["\']([0-9\s\-+]+)["\']', item, re.IGNORECASE)
                input_matches += re.findall(r'<input[^>]*\bvalue=["\']([0-9\s\-+]+)["\'][^>]*\bclass=["\'][^"\']*\bmsisdn\b[^"\']*["\']', item, re.IGNORECASE)
                for val in input_matches:
                    clean = re.sub(r'\D', '', val)
                    if len(clean) >= 9:
                        msisdns.append(clean[-9:])

                # 1B: data-(id|msisdn|number)
                data_matches = re.findall(r'data-(?:id|msisdn|number)=["\']?([0-9]{9,11})["\']?', item, re.IGNORECASE)
                for val in data_matches:
                    msisdns.append(val[-9:])

                # 1C: wywołanie changeAccountContext / changeContext w onclick/href
                call_matches = re.findall(r'(?:changeAccountContext|changeContext)\s*\(\s*["\']?([0-9]{9,11})["\']?', item, re.IGNORECASE)
                for val in call_matches:
                    msisdns.append(val[-9:])

                # 1D: <span> z numerem telefonu (np. <span>48 506 191 196</span> lub <span>506 191 196</span>)
                span_matches = re.findall(r'<span[^>]*>(?:(?:\+|00)?48[\s\-]*)?([0-9\s\-]{9,15})</span>', item, re.IGNORECASE)
                for val in span_matches:
                    clean = re.sub(r'\D', '', val)
                    if len(clean) >= 9:
                        msisdns.append(clean[-9:])

                # 1E: Formatowany numer w tagach > 48 XXX XXX XXX < lub > XXX XXX XXX <
                tag_matches = re.findall(r'>\s*(?:(?:\+|00)?48[\s\-]*)?([0-9]{3}[\s\-]?[0-9]{3}[\s\-]?[0-9]{3})\s*<', item)
                for val in tag_matches:
                    clean = re.sub(r'\D', '', val)
                    if len(clean) >= 9:
                        msisdns.append(clean[-9:])

        # Layer 2: DWR JS object properties (.msisdn="123456789" or msisdn:"123456789")
        if not msisdns:
            matches = re.findall(r'(?:msisdn|phoneNumber|number)[\s\.:=]+["\']?([0-9]{9,11})["\']?', text, re.IGNORECASE)
            for m in matches:
                msisdns.append(m[-9:])

        # Layer 3: DWR Array of string literals w wywołaniu handleCallback
        if not msisdns:
            arr_matches = re.findall(r'(?:handleCallback|_remoteHandleCallback)\([^)]*\[(.*?)\]', text, re.DOTALL)
            if not arr_matches:
                arr_matches = re.findall(r'\[(.*?)\]', text, re.DOTALL)
            for arr in arr_matches:
                items_in_arr = re.findall(r'["\'](?:\+?48)?([0-9]{9})["\']', arr)
                msisdns.extend(items_in_arr)

        deduped = list(dict.fromkeys(msisdns))
        _LOGGER.debug(f"[DIAG getContextMsisdns] Final extracted MSISDNs count: {len(deduped)}")
        return deduped

    async def async_change_account_context(self, msisdn: str) -> None:
        await self._async_dwr_request(
            "accountContextChangeService", 
            "changeAccountContext", 
            [f"string:{msisdn}", "string:ADMIN_CONTEXT"]
        )

    async def async_get_components_list(self, category: str) -> list[str]:
        text = await self._async_dwr_request(
            "servicesRemoteService", 
            "getComponentsList",
            [f"string:{category}"]
        )
        
        # Bezpieczne logi diagnostyczne struktury odpowiedzi
        props = list(dict.fromkeys(re.findall(r'(\w+)\s*[:=]\s*["\']', text)))
        _LOGGER.debug("Parsed active components response (response_length=%s, property_count=%s)", len(text), len(props))

        components = []

        # 1. Sprawdź HTML z dedykowanych pól widoku
        html = self._parse_dwr_html(text)
        
        # Dodatkowo: znajdź dowolne ciągi HTML w odpowiedzi DWR, niezależnie od nazwy właściwości
        html_chunks = [html] if html else []
        for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', text):
            raw = m.group(1)
            if '<' in raw and '>' in raw and re.search(r'<[a-zA-Z][^>]*>', raw):
                decoded = _decode_js_string(raw)
                decoded = decoded.replace('&quot;', '"').replace('&amp;', '&')
                html_chunks.append(decoded)

        full_html = "".join(html_chunks)
        if full_html:
            headings = re.findall(r'<h[2345][^>]*>(.*?)</h[2345]>', full_html, re.IGNORECASE)
            components.extend(headings)
            strongs = re.findall(r'<strong[^>]*>(.*?)</strong>', full_html, re.IGNORECASE)
            components.extend(strongs)
            titled = re.findall(r'class=["\'][^"\']*(?:title|service-name|component-name|header|service)[^"\']*["\'][^>]*>(.*?)<', full_html, re.IGNORECASE)
            components.extend(titled)
            data_named = re.findall(r'data-(?:name|title|service)=["\']([^"\']+)["\']', full_html, re.IGNORECASE)
            components.extend(data_named)

        # 2. Sprawdź właściwości obiektów JS w DWR
        # np. s1.name = "...", s1.componentName = "...", s1.title = "...", label, serviceLabel itp.
        js_prop_matches = re.findall(
            r'(?:\.|\b|["\'])(?:componentName|serviceName|displayName|name|title|label|header|serviceLabel|packageName)\b["\']?\s*[:=]\s*"([^"\\]+)"',
            text,
            re.IGNORECASE
        )
        components.extend(js_prop_matches)

        excluded_names = {
            "BaseDwrTransferData", "ServiceDwrResponse", "success", "0", 
            "PLAY24_ACTIVE_COMPONENTS_SECTION", "null", "undefined", "true", "false",
            "error", "OK", "STATUS_OK", "responseStatus", "ACTIVE", "INACTIVE"
        }

        # Czyszczenie i usunięcie tagów HTML
        cleaned = []
        for c in components:
            clean_str = re.sub(r'<[^>]+>', '', c).strip()
            if (clean_str 
                and len(clean_str) >= 3 
                and clean_str not in excluded_names 
                and not clean_str.isdigit()
                and not clean_str.startswith("http")):
                cleaned.append(clean_str)

        deduped = list(dict.fromkeys(cleaned))
        _LOGGER.debug("Extracted %s active component labels", len(deduped))
        return deduped

