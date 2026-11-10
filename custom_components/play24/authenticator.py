"""Authentication helper for Play24."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp

from .api import Play24AuthError, Play24ConnectionError

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup: Any = None

_LOGGER = logging.getLogger(__name__)


def _redact_url(url: str | None) -> str | None:
    if not url:
        return url
    secrets = ["code", "state", "session_code", "execution", "tab_id", "client_data"]
    redacted = str(url)
    for secret in secrets:
        redacted = re.sub(rf"({secret})=([^&]+)", r"\1=<REDACTED>", redacted)
    return redacted


def _extract_form_action(html: str) -> str | None:
    """Extract form action using BeautifulSoup or regex fallback."""
    if callable(BeautifulSoup):
        try:
            soup: Any = BeautifulSoup(html, "html.parser")
            form = soup.find("form")
            if form and form.get("action"):
                return str(form.get("action"))
        except (ValueError, TypeError, AttributeError) as err:
            _LOGGER.debug("BeautifulSoup form extraction error: %s", err)
    m = re.search(r'<form[^>]*\baction=["\']([^"\']+)["\']', html, re.IGNORECASE)
    return m.group(1) if m else None


def _validate_redirect_url(url: str | None) -> None:
    """Validate that redirect URL uses HTTPS and points to play.pl domain."""
    if not url:
        raise Play24AuthError("Disallowed redirect host")
    parsed = urlparse(url)
    host = (parsed.hostname or parsed.netloc.split(":")[0]).lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or not host
        or not (
            host == "play.pl"
            or (host.endswith(".play.pl") and not host.startswith("."))
        )
    ):
        _LOGGER.warning("Disallowed redirect URL blocked: %s", _redact_url(url))
        raise Play24AuthError("Disallowed redirect host")


validate_redirect_url = _validate_redirect_url


class Play24Authenticator:
    def __init__(self, session: aiohttp.ClientSession | None = None):
        self._custom_session = session
        self._cookie_jar: aiohttp.CookieJar | None = None
        self._action_url2: str | None = None
        self._referer: str | None = None

        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1",
        }

    @property
    def cookie_jar(self) -> aiohttp.CookieJar:
        if self._cookie_jar is None:
            self._cookie_jar = aiohttp.CookieJar(unsafe=True)
        return self._cookie_jar

    async def async_request_sms(self, msisdn: str) -> None:
        async with aiohttp.ClientSession(cookie_jar=self.cookie_jar) as session:
            # 1. GET 24.play.pl to initialize session and get redirect to login.play.pl
            url = "https://24.play.pl/Play24/"
            async with session.get(
                url, headers=self._headers, allow_redirects=True
            ) as resp:
                if "login.play.pl" not in str(resp.url):
                    raise Play24AuthError(
                        f"Failed to reach login.play.pl, landed on {resp.url}"
                    )

                text = await resp.text()
                action_url = _extract_form_action(text)
                if not action_url:
                    raise Play24AuthError("No form found on OIDC page")

            # 2. POST MSISDN
            data = {
                "errorSourcePageStep": "1",
                "errorSourceClientType": "",
                "msisdn": msisdn,
                "begin": "",
            }
            headers = dict(self._headers)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers["Referer"] = str(resp.url)

            async with session.post(action_url, data=data, headers=headers) as resp2:
                if resp2.status != 200:
                    raise Play24ConnectionError(
                        f"MSISDN POST failed with status {resp2.status}"
                    )
                text2 = await resp2.text()
                action_url2 = _extract_form_action(text2)
                if not action_url2:
                    raise Play24AuthError(
                        "No form found after MSISDN submit. WAF/Captcha block?"
                    )

                self._action_url2 = action_url2
                self._referer = str(resp2.url)

    async def async_submit_otp(self, otp: str) -> str:
        if not self._action_url2:
            raise Play24AuthError(
                "No action URL for OTP. Call async_request_sms first."
            )

        data = {
            "errorSourcePageStep": "3",
            "errorSourceClientType": "b2c",
            "otpCode": otp,
            "voice-otp-submit": "1",
        }
        headers = dict(self._headers)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = self._referer or ""

        async with aiohttp.ClientSession(cookie_jar=self.cookie_jar) as session:
            _LOGGER.debug("OTP POST to %s", _redact_url(self._action_url2))
            async with session.post(
                self._action_url2, data=data, headers=headers, allow_redirects=False
            ) as resp:
                _LOGGER.debug("OTP POST status: %s", resp.status)
                if resp.status == 200:
                    text = await resp.text()
                    action_url = _extract_form_action(text)
                    if action_url:
                        self._action_url2 = action_url
                        self._referer = str(resp.url)
                        _LOGGER.debug("Updated action_url2 for retry")
                    raise Play24AuthError("Błędny kod SMS (HTTP 200)")
                elif resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location")
                    _LOGGER.debug("OTP POST Location: %s", _redact_url(location))
                    if not location:
                        raise Play24AuthError("Redirect without Location header")
                else:
                    raise Play24AuthError(f"Unexpected OTP POST status: {resp.status}")

            # Follow redirects manually
            current_url = urljoin(str(resp.url), location)
            visited_urls = []
            while current_url:
                if current_url in visited_urls:
                    raise Play24AuthError(f"Redirect loop detected at {current_url}")
                visited_urls.append(current_url)

                parsed_redirect = urlparse(current_url)
                redirect_host = (
                    parsed_redirect.hostname
                    or (parsed_redirect.netloc.split(":")[0] if parsed_redirect.netloc else "")
                ).lower().rstrip(".")
                if (
                    parsed_redirect.scheme != "https"
                    or not redirect_host
                    or not (
                        redirect_host == "play.pl"
                        or (redirect_host.endswith(".play.pl") and not redirect_host.startswith("."))
                    )
                ):
                    _LOGGER.warning("Disallowed redirect URL blocked: %s", _redact_url(current_url))
                    raise Play24AuthError("Disallowed redirect host")

                _LOGGER.debug("Following redirect to: %s", _redact_url(current_url))
                async with session.get(
                    current_url, headers=self._headers, allow_redirects=False
                ) as redirect_resp:
                    _LOGGER.debug("Redirect GET status: %s", redirect_resp.status)

                    if redirect_resp.status in (301, 302, 303, 307, 308):
                        loc = redirect_resp.headers.get("Location")
                        if not loc:
                            _LOGGER.debug("Redirect status but no Location header")
                            break
                        if "error/500" in loc:
                            raise Play24AuthError("Got 500 error from authCode")

                        current_url = urljoin(str(redirect_resp.url), loc)
                        _LOGGER.debug(
                            "Next redirect URL resolved to: %s",
                            _redact_url(current_url),
                        )
                    elif redirect_resp.status == 200:
                        break
                    else:
                        raise Play24AuthError(
                            f"Unexpected status {redirect_resp.status} on {current_url}"
                        )

            for cookie in session.cookie_jar:
                if cookie.key == "JSESSIONID":
                    return cookie.value

            raise Play24AuthError("JSESSIONID not found after manual redirect chain")
