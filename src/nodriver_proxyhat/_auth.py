"""Wire ProxyHat gateway authentication onto a nodriver tab over raw CDP.

Chrome's ``--proxy-server`` flag can't carry a username/password, so a credentialed
residential gateway needs another way to answer the proxy's auth challenge. nodriver
speaks the Chrome DevTools Protocol directly, so we authenticate the CDP way:

1. enable the ``Fetch`` domain with ``handle_auth_requests=True``,
2. answer every ``Fetch.authRequired`` with the ProxyHat targeting username +
   sub-user password via ``Fetch.continueWithAuth`` (``ProvideCredentials``),
3. resume every other paused request with ``Fetch.continueRequest``.

Enabling ``Fetch`` pauses *every* request (a ``requestPaused`` event), so the
non-auth requests must be continued too or the page hangs waiting on us.

This is the HTTP gateway path (port 8080) — CDP proxy auth answers the HTTP
proxy's basic-auth challenge. ``nodriver`` is imported lazily so importing this
module never requires it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nodriver import Tab

# The Fetch handlers below fire asynchronously and may still be in flight when the
# browser starts shutting down: Fetch gets disabled, then the CDP connection and
# event loop close. A ``continue_request`` / ``continue_with_auth`` that lands in
# that window raises a benign error — there's simply nothing left to answer — and
# nodriver leaks its traceback to stderr. These substrings mark those shutdown-race
# errors (a disabled Fetch domain, a closed CDP socket, a closed event loop) so we
# can swallow just those; every other error propagates so real auth/protocol
# failures stay visible.
_TEARDOWN_RACE_MARKERS = (
    "fetch domain is not enabled",
    "websocket is not connected",
    "connection is closed",
    "connection closed",
    "event loop is closed",
    "no running event loop",
)


async def _send_quiet(tab: Tab, command: object) -> None:
    """Send a CDP command, swallowing only benign browser-teardown races.

    Normal operation is unchanged: on a live tab the send succeeds. Only when the
    send fails with a known shutdown-race error (see ``_TEARDOWN_RACE_MARKERS``) is
    the exception suppressed; anything else re-raises.
    """
    try:
        await tab.send(command)
    except Exception as exc:  # noqa: BLE001 - re-raised unless it's a teardown race
        if any(marker in str(exc).lower() for marker in _TEARDOWN_RACE_MARKERS):
            return
        raise


async def enable_proxy_auth(tab: Tab, username: str, password: str) -> None:
    """Register the CDP proxy-auth handlers on ``tab`` and enable ``Fetch``.

    Adds a ``Fetch.authRequired`` handler that answers with ``username`` /
    ``password`` and a ``Fetch.requestPaused`` handler that resumes normal
    requests, then enables the Fetch domain with auth handling. Call once per tab
    before navigating so the very first request is authenticated.
    """
    from nodriver import cdp

    async def _on_auth_required(event: cdp.fetch.AuthRequired) -> None:
        await _send_quiet(
            tab,
            cdp.fetch.continue_with_auth(
                request_id=event.request_id,
                auth_challenge_response=cdp.network.AuthChallengeResponse(
                    response="ProvideCredentials",
                    username=username,
                    password=password,
                ),
            ),
        )

    async def _on_request_paused(event: cdp.fetch.RequestPaused) -> None:
        await _send_quiet(tab, cdp.fetch.continue_request(request_id=event.request_id))

    tab.add_handler(cdp.fetch.AuthRequired, _on_auth_required)
    tab.add_handler(cdp.fetch.RequestPaused, _on_request_paused)
    await tab.send(cdp.fetch.enable(handle_auth_requests=True))
