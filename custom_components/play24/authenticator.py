import aiohttp
import re
from typing import Dict, Optional, Tuple
import logging
from .api import Play24AuthError

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

_LOGGER = logging.getLogger(__name__)

def _redact_url(url: str) -> str:
    if not url:
        return url
    secrets = ['code', 'state', 'session_code', 'execution', 'tab_id', 'client_data']
    for secret in secrets:
        url = re.sub(rf'({secret})=([^&]+)', rf'\1=<REDACTED>', str(url))
    return url

def _extract_form_action(html: str) -> Optional[str]:
    """Extract form action using BeautifulSoup or regex fallback."""
    if BeautifulSoup:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            form = soup.find('form')
            if form and form.get('action'):
                return form.get('action')
        except Exception:
            pass
    m = re.search(r'<form[^>]*\baction=["\']([^"\']+)["\']', html, re.IGNORECASE)
    return m.group(1) if m else None

class Play24Authenticator:
    def __init__(self):
        self._cookie_jar: Optional[aiohttp.CookieJar] = None
        self._action_url2: Optional[str] = None
        self._referer: Optional[str] = None
        
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1"
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
            async with session.get(url, headers=self._headers, allow_redirects=True) as resp:
                if "login.play.pl" not in str(resp.url):
                    raise Exception(f"Failed to reach login.play.pl, landed on {resp.url}")
                
                text = await resp.text()
                action_url = _extract_form_action(text)
                if not action_url:
                    raise Exception("No form found on OIDC page")
                
            # 2. POST MSISDN
            data = {
                "errorSourcePageStep": "1",
                "errorSourceClientType": "",
                "msisdn": msisdn,
                "begin": ""
            }
            headers = dict(self._headers)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers["Referer"] = str(resp.url)
            
            async with session.post(action_url, data=data, headers=headers) as resp2:
                if resp2.status != 200:
                    raise Exception(f"MSISDN POST failed with status {resp2.status}")
                text2 = await resp2.text()
                action_url2 = _extract_form_action(text2)
                if not action_url2:
                    raise Exception("No form found after MSISDN submit. WAF/Captcha block?")
                
                self._action_url2 = action_url2
                self._referer = str(resp2.url)

    async def async_submit_otp(self, otp: str) -> str:
        if not self._action_url2:
            raise Exception("No action URL for OTP. Call async_request_sms first.")
            
        data = {
            "errorSourcePageStep": "3",
            "errorSourceClientType": "b2c",
            "otpCode": otp,
            "voice-otp-submit": "1"
        }
        headers = dict(self._headers)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = self._referer
        
        async with aiohttp.ClientSession(cookie_jar=self.cookie_jar) as session:
            _LOGGER.debug("OTP POST to %s", _redact_url(self._action_url2))
            async with session.post(self._action_url2, data=data, headers=headers, allow_redirects=False) as resp:
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
                        raise Exception("Redirect without Location header")
                else:
                    raise Exception(f"Unexpected OTP POST status: {resp.status}")
            
            # Follow redirects manually
            current_url = location
            visited_urls = []
            while current_url:
                if current_url in visited_urls:
                    raise Exception(f"Redirect loop detected at {current_url}")
                visited_urls.append(current_url)
                
                _LOGGER.debug("Following redirect to: %s", _redact_url(current_url))
                async with session.get(current_url, headers=self._headers, allow_redirects=False) as redirect_resp:
                    _LOGGER.debug("Redirect GET status: %s", redirect_resp.status)
                    
                    if redirect_resp.status in (301, 302, 303, 307, 308):
                        loc = redirect_resp.headers.get("Location")
                        if not loc:
                            _LOGGER.debug("Redirect status but no Location header")
                            break
                        if 'error/500' in loc:
                            raise Exception("Got 500 error from authCode")
                            
                        from urllib.parse import urljoin
                        current_url = urljoin(str(redirect_resp.url), loc)
                        _LOGGER.debug("Next redirect URL resolved to: %s", _redact_url(current_url))
                    elif redirect_resp.status == 200:
                        break
                    else:
                        raise Exception(f"Unexpected status {redirect_resp.status} on {current_url}")
            
            for cookie in session.cookie_jar:
                if cookie.key == "JSESSIONID":
                    return cookie.value
                    
            raise Exception("JSESSIONID not found after manual redirect chain")
