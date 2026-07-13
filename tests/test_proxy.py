"""Offline tests for the proxy-args / auth / credential surface.

No browser is launched and no network call is made: the ProxyHat SDK's
``sub_users.list()`` is mocked, and we assert the ``--proxy-server`` flag and the
targeting username (geo + sticky reflected) + password directly.
"""

from types import SimpleNamespace

import pytest

from nodriver_proxyhat import (
    ProxyHatConfigError,
    proxyhat_auth,
    proxyhat_browser_args,
    resolve_credentials,
)


def sub_user(**kw):
    base = dict(
        uuid="u",
        name=None,
        proxy_username="ph-1",
        proxy_password="pw",
        traffic_limit=0,
        used_traffic=0,
        suspended_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestBrowserArgs:
    def test_sets_http_gateway_proxy_server(self):
        assert proxyhat_browser_args() == ["--proxy-server=gate.proxyhat.com:8080"]

    def test_targeting_kwargs_do_not_change_the_flag(self):
        # Targeting lives in the CDP auth username, not the --proxy-server flag.
        args = proxyhat_browser_args(country="de", sticky=False, filter="high")
        assert args == ["--proxy-server=gate.proxyhat.com:8080"]


class TestAuth:
    def test_returns_targeting_username_and_password(self):
        user, pw = proxyhat_auth(username="ph-1", password="pw", country="us")
        assert user.startswith("ph-1-country-us")
        assert pw == "pw"

    def test_sticky_default_pins_session(self):
        user, _ = proxyhat_auth(username="ph-1", password="pw")
        # Default is sticky: a session id + 30m TTL is present.
        assert "-sid-" in user
        assert "-ttl-30m" in user

    def test_sticky_false_is_rotating(self):
        user, _ = proxyhat_auth(username="ph-1", password="pw", sticky=False)
        assert "-sid-" not in user
        assert "-ttl-" not in user

    def test_custom_sticky_ttl(self):
        user, _ = proxyhat_auth(username="ph-1", password="pw", sticky="2h")
        assert "-ttl-2h" in user

    def test_geo_targeting(self):
        user, _ = proxyhat_auth(
            username="ph-1",
            password="pw",
            country="de",
            region="berlin",
            city="berlin",
            filter="high",
            sticky=False,
        )
        assert user == "ph-1-country-de-region-berlin-city-berlin-filter-high"


class TestCredentialResolution:
    def test_explicit_username_password(self):
        assert resolve_credentials(username="ph-1", password="pw") == ("ph-1", "pw")

    def test_raises_without_credentials(self, monkeypatch):
        for var in ("PROXYHAT_API_KEY", "PROXYHAT_USERNAME", "PROXYHAT_PASSWORD", "PROXYHAT_SUBUSER"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(ProxyHatConfigError):
            resolve_credentials()

    def test_api_key_picks_active_sub_user(self, monkeypatch):
        users = [
            sub_user(uuid="s", proxy_username="susp", suspended_at="2026-01-01"),
            sub_user(uuid="g", proxy_username="good", traffic_limit=100, used_traffic=100),
            sub_user(uuid="ok", proxy_username="ok", traffic_limit=100, used_traffic=1),
        ]
        fake_client = SimpleNamespace(sub_users=SimpleNamespace(list=lambda: users))
        monkeypatch.setattr("nodriver_proxyhat._resolve.ProxyHat", lambda **kw: fake_client)
        assert resolve_credentials(api_key="ph_key") == ("ok", "pw")

    def test_api_key_named_sub_user(self, monkeypatch):
        users = [sub_user(uuid="a", proxy_username="a"), sub_user(uuid="b", name="prod", proxy_username="b")]
        fake_client = SimpleNamespace(sub_users=SimpleNamespace(list=lambda: users))
        monkeypatch.setattr("nodriver_proxyhat._resolve.ProxyHat", lambda **kw: fake_client)
        assert resolve_credentials(api_key="ph_key", sub_user="prod") == ("b", "pw")

    def test_api_key_no_usable_sub_user(self, monkeypatch):
        users = [sub_user(traffic_limit=100, used_traffic=100)]
        fake_client = SimpleNamespace(sub_users=SimpleNamespace(list=lambda: users))
        monkeypatch.setattr("nodriver_proxyhat._resolve.ProxyHat", lambda **kw: fake_client)
        with pytest.raises(ProxyHatConfigError):
            resolve_credentials(api_key="ph_key")

    def test_proxyhat_auth_resolves_via_api_key(self, monkeypatch):
        users = [sub_user(proxy_username="good", proxy_password="secret")]
        fake_client = SimpleNamespace(sub_users=SimpleNamespace(list=lambda: users))
        monkeypatch.setattr("nodriver_proxyhat._resolve.ProxyHat", lambda **kw: fake_client)
        user, pw = proxyhat_auth(api_key="ph_key", country="us", sticky=False)
        assert user == "good-country-us"
        assert pw == "secret"
