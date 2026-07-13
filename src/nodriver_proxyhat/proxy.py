"""Route a nodriver (undetected Chrome) browser through the ProxyHat gateway.

nodriver launches Chrome with ``nodriver.start(browser_args=[...])``, but Chrome's
``--proxy-server`` flag can't carry a username/password. nodriver gives raw CDP
access, so the credentialed residential gateway is authenticated the CDP way:
enable the Fetch domain with ``handle_auth_requests=True`` and answer
``Fetch.authRequired`` with the ProxyHat targeting username + sub-user password
(see :mod:`nodriver_proxyhat._auth`).

Three entry points:

- ``proxyhat_browser_args()`` — the ``--proxy-server`` launch flag for the gateway.
- ``proxyhat_auth()`` — the ``(username, password)`` for wiring the CDP auth
  handler yourself.
- ``proxyhat_browser()`` — start Chrome with the flag applied *and* the CDP auth
  handler already wired.

This is the HTTP gateway (port 8080); CDP proxy auth applies to the HTTP proxy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from proxyhat import (
    PROXYHAT_GATEWAY,
    PROXYHAT_PORT_HTTP,
    build_proxy_username,
)

from nodriver_proxyhat._auth import enable_proxy_auth
from nodriver_proxyhat._resolve import resolve_credentials

if TYPE_CHECKING:
    from nodriver import Browser

# A browser session takes many steps against the same site, so pin one
# residential IP for the whole session by default — keeps cookies and
# fingerprint consistent. sticky=False rotates a fresh IP per connection.
DEFAULT_STICKY = "30m"


def proxyhat_browser_args(**_targeting: Any) -> list[str]:
    """Return the Chrome launch args pointing nodriver at the ProxyHat gateway.

    Just ``["--proxy-server=gate.proxyhat.com:8080"]`` — the HTTP gateway host and
    port. Targeting (``country`` / ``region`` / ``city`` / ``sticky`` / ``filter``)
    is *not* encoded here, because Chrome's ``--proxy-server`` can't carry it: it
    lives in the CDP auth username built by :func:`proxyhat_auth` and applied by
    :func:`proxyhat_browser`. Targeting keyword arguments are accepted (so you can
    splat the same dict you pass to those) but do not change the returned flag.

    Merge the result into your own ``nodriver.start(browser_args=[...])`` call and
    wire auth yourself with :func:`proxyhat_auth` + ``enable_proxy_auth`` — or just
    use :func:`proxyhat_browser`, which does both.
    """
    return [f"--proxy-server={PROXYHAT_GATEWAY}:{PROXYHAT_PORT_HTTP}"]


def proxyhat_auth(
    *,
    api_key: str | None = None,
    username: str | None = None,
    password: str | None = None,
    sub_user: str | None = None,
    country: str | None = None,
    region: str | None = None,
    city: str | None = None,
    sticky: bool | str | None = DEFAULT_STICKY,
    filter: str | None = None,
) -> tuple[str, str]:
    """Resolve the ``(gateway_username, password)`` for the ProxyHat gateway.

    Resolves credentials (``api_key`` / ``PROXYHAT_API_KEY`` auto-picks an active
    sub-user, or pass explicit ``username`` / ``password``), then builds the
    targeting username — geo and stickiness reflected — with the official
    ``proxyhat`` SDK grammar. Feed the pair to a CDP ``Fetch.authRequired`` handler
    (``ProvideCredentials``) if you're wiring nodriver yourself; otherwise
    :func:`proxyhat_browser` does it for you.

    Sticky vs rotating:

    - ``sticky="30m"`` (default) or ``sticky=True`` pins one residential IP for
      the session — recommended for a browser.
    - ``sticky=False`` (or ``None``) rotates: a fresh residential IP per connection.
    - ``sticky="2h"`` sets a custom session lifetime.

    Geo/quality targeting: ``country`` (ISO code or ``"any"``), ``region``,
    ``city``, ``filter`` (AI IP-quality tier).
    """
    user, pw = resolve_credentials(
        api_key=api_key,
        username=username,
        password=password,
        sub_user=sub_user,
    )
    # Build the targeting username once so a sticky session mints a single sid
    # shared by every request the browser makes.
    gateway_username = build_proxy_username(
        user,
        country=country,
        region=region,
        city=city,
        sticky=sticky,
        filter=filter,
    )
    return gateway_username, pw


async def proxyhat_browser(
    *,
    api_key: str | None = None,
    username: str | None = None,
    password: str | None = None,
    sub_user: str | None = None,
    country: str | None = None,
    region: str | None = None,
    city: str | None = None,
    sticky: bool | str | None = DEFAULT_STICKY,
    filter: str | None = None,
    **start_kwargs: Any,
) -> Browser:
    """Start a nodriver Chrome routed through ProxyHat with gateway auth wired.

    Resolves credentials, calls ``nodriver.start(browser_args=[...], **start_kwargs)``
    with the ``--proxy-server`` flag applied, then enables CDP ``Fetch`` on the
    browser's main tab and registers a ``Fetch.authRequired`` handler that answers
    with the ProxyHat targeting username + sub-user password. Returns the started
    ``Browser`` — navigate with ``await browser.get(url)``.

    Any extra keyword arguments (``headless``, ``user_data_dir``, ``sandbox``, …)
    are forwarded to ``nodriver.start``; if you pass your own ``browser_args`` they
    are merged with the ProxyHat flag. Sticky by default (one pinned IP for the
    whole session); pass ``sticky=False`` for a rotating IP. See :func:`proxyhat_auth`
    for the full targeting keyword set.

    ``nodriver`` is imported lazily — install it (``pip install nodriver-proxyhat[nodriver]``)
    to use this helper; :func:`proxyhat_browser_args` and :func:`proxyhat_auth` work
    without it.
    """
    gateway_username, pw = proxyhat_auth(
        api_key=api_key,
        username=username,
        password=password,
        sub_user=sub_user,
        country=country,
        region=region,
        city=city,
        sticky=sticky,
        filter=filter,
    )

    caller_args = start_kwargs.pop("browser_args", None) or []
    browser_args = proxyhat_browser_args() + list(caller_args)

    # Imported lazily: nodriver is an optional (peer) dependency, so importing
    # this module never forces a Chrome/nodriver install.
    import nodriver

    browser = await nodriver.start(browser_args=browser_args, **start_kwargs)
    await enable_proxy_auth(browser.main_tab, gateway_username, pw)
    return browser
