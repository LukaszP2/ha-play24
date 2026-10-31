import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aiohttp import CookieJar
import aiohttp
from custom_components.play24.authenticator import Play24Authenticator

@pytest.fixture
def auth():
    return Play24Authenticator()

@pytest.mark.asyncio
async def test_request_sms_success(auth):
    # Mock first GET to OIDC
    mock_resp1 = MagicMock()
    mock_resp1.status = 200
    mock_resp1.text = AsyncMock(return_value='<form action="https://login.play.pl/auth/action1"></form>')
    mock_resp1.url = "https://login.play.pl/auth/oidc"
    
    # Mock POST MSISDN
    mock_resp2 = MagicMock()
    mock_resp2.status = 200
    mock_resp2.text = AsyncMock(return_value='<form action="https://login.play.pl/auth/action2">otp</form>')
    mock_resp2.url = "https://login.play.pl/auth/action1"

    with patch("aiohttp.ClientSession.get", return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_resp1), __aexit__=AsyncMock(return_value=None))) as mock_get:
        with patch("aiohttp.ClientSession.post", return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_resp2), __aexit__=AsyncMock(return_value=None))) as mock_post:
            await auth.async_request_sms("500123456")
            
            assert mock_get.call_count == 1
            assert mock_post.call_count == 1
            assert auth._action_url2 == "https://login.play.pl/auth/action2"
            assert auth._referer == "https://login.play.pl/auth/action1"

@pytest.mark.asyncio
async def test_submit_otp_success(auth):
    auth._action_url2 = "https://login.play.pl/auth/action2"
    auth._referer = "https://login.play.pl/auth/action1"
    
    mock_resp_post = MagicMock()
    mock_resp_post.status = 302
    mock_resp_post.url = "https://login.play.pl/auth/action2"
    mock_resp_post.headers = {"Location": "https://24.play.pl/Play24/Welcome"}
    mock_resp_post.text = AsyncMock(return_value="")
    
    mock_resp_get = MagicMock()
    mock_resp_get.status = 200
    mock_resp_get.url = "https://24.play.pl/Play24/Welcome"
    mock_resp_get.headers = {}
    mock_resp_get.text = AsyncMock(return_value="")

    mock_cookie = MagicMock()
    mock_cookie.key = "JSESSIONID"
    mock_cookie.value = "mock_jsessionid"
    
    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp_post)
        mock_session_instance.post.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session_instance.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp_get)
        mock_session_instance.get.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session_instance.cookie_jar = [mock_cookie]
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        jsessionid = await auth.async_submit_otp("123456")
        
        assert jsessionid == "mock_jsessionid"
        mock_session_instance.post.assert_called_once()
        args, kwargs = mock_session_instance.post.call_args
        assert args[0] == "https://login.play.pl/auth/action2"
        assert kwargs["data"]["otpCode"] == "123456"

@pytest.mark.asyncio
async def test_submit_otp_fail(auth):
    auth._action_url2 = "https://login.play.pl/auth/action2"
    
    mock_resp_post = MagicMock()
    mock_resp_post.status = 302
    mock_resp_post.url = "https://login.play.pl/auth/action2"
    mock_resp_post.headers = {"Location": "https://24.play.pl/Play24/Welcome"}
    mock_resp_post.text = AsyncMock(return_value="")
    
    mock_resp_get = MagicMock()
    mock_resp_get.status = 200
    mock_resp_get.url = "https://24.play.pl/Play24/Welcome"
    mock_resp_get.headers = {}
    mock_resp_get.text = AsyncMock(return_value="")

    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session_instance = MagicMock()
        mock_session_instance.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp_post)
        mock_session_instance.post.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session_instance.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp_get)
        mock_session_instance.get.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session_instance.cookie_jar = []
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)
        
        with pytest.raises(Exception, match="JSESSIONID not found"):
            await auth.async_submit_otp("123456")
