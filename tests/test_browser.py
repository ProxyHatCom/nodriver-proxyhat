"""Tests for the CDP auth wiring and proxyhat_browser.

nodriver drives a real Chrome, so instead of installing it we inject a tiny fake
``nodriver`` module (with a ``cdp.fetch`` / ``cdp.network`` surface) that records
the CDP commands our code sends. That exercises the actual auth-handler path —
Fetch.enable, the Fetch.authRequired answer, and request resumption — plus the
browser_args / start_kwargs wiring, without any browser or network.
"""

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

from nodriver_proxyhat import enable_proxy_auth, proxyhat_browser


def run(coro):
    return asyncio.run(coro)


class FakeTab:
    def __init__(self):
        self.handlers = {}
        self.sent = []

    def add_handler(self, event_type, callback):
        self.handlers[event_type] = callback

    async def send(self, command):
        self.sent.append(command)


class FakeBrowser:
    def __init__(self):
        self.main_tab = FakeTab()


class AuthChallengeResponse:
    def __init__(self, *, response, username=None, password=None):
        self.response = response
        self.username = username
        self.password = password


class AuthRequired:
    """Stand-in for cdp.fetch.AuthRequired event type."""


class RequestPaused:
    """Stand-in for cdp.fetch.RequestPaused event type."""


@pytest.fixture
def fake_nodriver(monkeypatch):
    """Install a fake ``nodriver`` module and return a handle to inspect it."""
    captured = {}

    fetch = ModuleType("nodriver.cdp.fetch")
    fetch.AuthRequired = AuthRequired
    fetch.RequestPaused = RequestPaused
    fetch.enable = lambda **kw: ("fetch.enable", kw)
    fetch.continue_with_auth = lambda **kw: ("fetch.continue_with_auth", kw)
    fetch.continue_request = lambda **kw: ("fetch.continue_request", kw)

    network = ModuleType("nodriver.cdp.network")
    network.AuthChallengeResponse = AuthChallengeResponse

    cdp = ModuleType("nodriver.cdp")
    cdp.fetch = fetch
    cdp.network = network

    nodriver = ModuleType("nodriver")
    nodriver.cdp = cdp

    browser = FakeBrowser()

    async def start(**kwargs):
        captured["start_kwargs"] = kwargs
        return browser

    nodriver.start = start

    monkeypatch.setitem(sys.modules, "nodriver", nodriver)
    monkeypatch.setitem(sys.modules, "nodriver.cdp", cdp)
    monkeypatch.setitem(sys.modules, "nodriver.cdp.fetch", fetch)
    monkeypatch.setitem(sys.modules, "nodriver.cdp.network", network)
    return SimpleNamespace(module=nodriver, browser=browser, captured=captured)


class TestEnableProxyAuth:
    def test_registers_handlers_and_enables_fetch(self, fake_nodriver):
        tab = FakeTab()
        run(enable_proxy_auth(tab, "ph-1-country-us", "pw"))

        assert AuthRequired in tab.handlers
        assert RequestPaused in tab.handlers
        # Fetch enabled with auth handling requested.
        assert ("fetch.enable", {"handle_auth_requests": True}) in tab.sent

    def test_auth_handler_answers_with_credentials(self, fake_nodriver):
        tab = FakeTab()
        run(enable_proxy_auth(tab, "ph-1-country-us-sid-abc-ttl-30m", "s3cr3t"))

        event = SimpleNamespace(request_id="req-1")
        run(tab.handlers[AuthRequired](event))

        name, kw = tab.sent[-1]
        assert name == "fetch.continue_with_auth"
        assert kw["request_id"] == "req-1"
        acr = kw["auth_challenge_response"]
        assert acr.response == "ProvideCredentials"
        assert acr.username == "ph-1-country-us-sid-abc-ttl-30m"
        assert acr.password == "s3cr3t"

    def test_request_handler_resumes_paused_requests(self, fake_nodriver):
        tab = FakeTab()
        run(enable_proxy_auth(tab, "ph-1", "pw"))

        event = SimpleNamespace(request_id="req-2")
        run(tab.handlers[RequestPaused](event))

        assert ("fetch.continue_request", {"request_id": "req-2"}) in tab.sent


class TestProxyhatBrowser:
    def test_applies_proxy_flag_and_wires_auth(self, fake_nodriver):
        browser = run(proxyhat_browser(username="ph-1", password="pw", country="us"))
        assert browser is fake_nodriver.browser

        start_kwargs = fake_nodriver.captured["start_kwargs"]
        assert "--proxy-server=gate.proxyhat.com:8080" in start_kwargs["browser_args"]

        tab = browser.main_tab
        # Auth handler was wired and Fetch enabled on the main tab.
        assert AuthRequired in tab.handlers
        assert ("fetch.enable", {"handle_auth_requests": True}) in tab.sent

        # The wired handler answers with the sticky, geo-targeted username.
        run(tab.handlers[AuthRequired](SimpleNamespace(request_id="r")))
        _, kw = tab.sent[-1]
        acr = kw["auth_challenge_response"]
        assert acr.username.startswith("ph-1-country-us")
        assert "-sid-" in acr.username  # sticky by default
        assert acr.password == "pw"

    def test_forwards_start_kwargs_and_merges_browser_args(self, fake_nodriver):
        run(
            proxyhat_browser(
                username="ph-1",
                password="pw",
                headless=True,
                browser_args=["--window-size=1920,1080"],
            )
        )
        start_kwargs = fake_nodriver.captured["start_kwargs"]
        assert start_kwargs["headless"] is True
        assert "--proxy-server=gate.proxyhat.com:8080" in start_kwargs["browser_args"]
        assert "--window-size=1920,1080" in start_kwargs["browser_args"]

    def test_rotating_option(self, fake_nodriver):
        browser = run(proxyhat_browser(username="ph-1", password="pw", sticky=False))
        tab = browser.main_tab
        run(tab.handlers[AuthRequired](SimpleNamespace(request_id="r")))
        _, kw = tab.sent[-1]
        assert "-sid-" not in kw["auth_challenge_response"].username

    def test_resolves_via_api_key(self, fake_nodriver, monkeypatch):
        users = [
            SimpleNamespace(
                uuid="u",
                name=None,
                proxy_username="good",
                proxy_password="secret",
                traffic_limit=0,
                used_traffic=0,
                suspended_at=None,
            )
        ]
        fake_client = SimpleNamespace(sub_users=SimpleNamespace(list=lambda: users))
        monkeypatch.setattr("nodriver_proxyhat._resolve.ProxyHat", lambda **kw: fake_client)

        browser = run(proxyhat_browser(api_key="ph_key", country="us", sticky=False))
        tab = browser.main_tab
        run(tab.handlers[AuthRequired](SimpleNamespace(request_id="r")))
        _, kw = tab.sent[-1]
        acr = kw["auth_challenge_response"]
        assert acr.username == "good-country-us"
        assert acr.password == "secret"
