# nodriver-proxyhat

Route [nodriver](https://github.com/ultrafunkamsterdam/nodriver) — the successor to undetected-chromedriver — through [ProxyHat](https://proxyhat.com?utm_source=github&utm_medium=readme&utm_campaign=nodriver) residential proxies. **Authenticated** gateway proxies wired straight into nodriver over CDP, plus a sticky residential IP pinned for the whole session, geo-targeting, and rotation.

[![CI](https://github.com/ProxyHatCom/nodriver-proxyhat/actions/workflows/ci.yml/badge.svg)](https://github.com/ProxyHatCom/nodriver-proxyhat/actions/workflows/ci.yml)
[![Compatible with nodriver latest](https://github.com/ProxyHatCom/nodriver-proxyhat/actions/workflows/compat.yml/badge.svg)](https://github.com/ProxyHatCom/nodriver-proxyhat/actions/workflows/compat.yml)
[![PyPI](https://img.shields.io/pypi/v/nodriver-proxyhat)](https://pypi.org/project/nodriver-proxyhat/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> [!TIP]
> **Recommended proxies — [ProxyHat](https://proxyhat.com?utm_source=github&utm_medium=readme&utm_campaign=nodriver&utm_content=callout) residential IPs.** Every feature in this package is tested end-to-end against ProxyHat and works great. First-class integration; also works with any proxy, or none.


## Why

Chrome's `--proxy-server` flag **can't carry a username and password**, so pointing an undetected browser at a credentialed residential gateway normally means a manual CDP dance. And running a real browser from a datacenter IP gets flagged, CAPTCHA-walled, and blocked anyway — exactly what you're using nodriver to avoid.

`nodriver-proxyhat` fixes both. It plugs ProxyHat's residential IPs (50M+ across 148+ countries) into nodriver and handles gateway auth the CDP way nodriver is built for: it enables the **Fetch** domain and answers the proxy's `Fetch.authRequired` challenge with your credentials. One pinned residential IP per session by default, so cookies and fingerprint stay consistent while your script works.

## Install

```bash
pip install nodriver-proxyhat nodriver
```

`nodriver` is a peer dependency — bring your own version (and its Chrome). The `proxyhat_browser_args()` / `proxyhat_auth()` helpers work without it; `proxyhat_browser()` needs nodriver installed.

## Quick start

```python
import nodriver as uc
from nodriver_proxyhat import proxyhat_browser

async def main():
    # An API key (PROXYHAT_API_KEY) auto-selects an active residential sub-user:
    browser = await proxyhat_browser(country="us")   # sticky US IP for the whole session
    page = await browser.get("https://httpbin.org/ip")
    print(await page.get_content())
    browser.stop()

uc.loop().run_until_complete(main())
```

Get an API key at [proxyhat.com](https://proxyhat.com?utm_source=github&utm_medium=readme&utm_campaign=nodriver).

`proxyhat_browser(...)` calls `nodriver.start(...)` for you and forwards any extra keyword arguments (`headless`, `user_data_dir`, `browser_args`, …) unchanged.

## Credentials

Pass them explicitly or via environment variables — options win over env:

| Option | Env var | Notes |
|---|---|---|
| `api_key` | `PROXYHAT_API_KEY` | Auto-selects an active sub-user with remaining traffic |
| `sub_user` | `PROXYHAT_SUBUSER` | Pick a specific sub-user by uuid or name (with an API key) |
| `username` | `PROXYHAT_USERNAME` | Explicit gateway `proxy_username` (skips the API) |
| `password` | `PROXYHAT_PASSWORD` | Explicit gateway `proxy_password` |

## Targeting

```python
await proxyhat_browser(
    country="us",      # ISO code or "any" (default)
    region="california",
    city="new_york",
    filter="high",     # AI IP-quality tier
    sticky="30m",      # session lifetime (default); sticky=False rotates every request
    headless=True,     # any extra kwarg is forwarded to nodriver.start
)
```

The same targeting keyword arguments work on `proxyhat_auth(...)`.

### Sticky IP per session (default)

A browser session takes many steps against the same site — logging in, clicking, scrolling. If the exit IP changed mid-session the site would see a user teleporting between cities and block it. So this package is **sticky by default**: one residential IP is pinned for the whole session (`sticky="30m"`, renewed as you work), keeping cookies and fingerprint coherent.

Want a fresh IP on **every** request instead (e.g. many independent one-shot fetches)? Turn stickiness off:

```python
await proxyhat_browser(country="us", sticky=False)  # rotating residential IP per connection
```

Set a custom lifetime with `sticky="2h"`.

## How authentication works

nodriver takes the proxy host/port from `--proxy-server=gate.proxyhat.com:8080`, but a residential gateway also needs a username (the ProxyHat targeting string) and password. Since the flag can't carry them, `proxyhat_browser` uses nodriver's raw Chrome DevTools Protocol access instead:

1. it enables the **Fetch** domain on the main tab with `handle_auth_requests=True`;
2. it registers a `Fetch.authRequired` handler that answers with your targeting username + sub-user password via `Fetch.continueWithAuth` (`ProvideCredentials`);
3. it resumes every other paused request with `Fetch.continueRequest` (enabling Fetch pauses all requests, so non-auth ones must be continued too).

The targeting username (e.g. `<user>-country-us-sid-<id>-ttl-30m`) is built by the official [`proxyhat`](https://pypi.org/project/proxyhat/) SDK, so a sticky session mints a single session id shared across the run.

This is the **HTTP gateway** (port 8080) — CDP proxy auth answers the HTTP proxy's basic-auth challenge.

## Wiring it yourself

Prefer to drive `nodriver.start()` your way? Grab the launch flag and the resolved credentials and wire the CDP handler yourself:

```python
import nodriver as uc
from nodriver import cdp
from nodriver_proxyhat import proxyhat_auth, proxyhat_browser_args, enable_proxy_auth

async def main():
    username, password = proxyhat_auth(country="de", sticky="1h")

    browser = await uc.start(browser_args=proxyhat_browser_args() + ["--headless=new"])
    # enable_proxy_auth does the Fetch.enable + authRequired dance for you:
    await enable_proxy_auth(browser.main_tab, username, password)

    page = await browser.get("https://httpbin.org/ip")
    print(await page.get_content())
    browser.stop()

uc.loop().run_until_complete(main())
```

`proxyhat_browser_args()` returns `["--proxy-server=gate.proxyhat.com:8080"]`; `proxyhat_auth()` returns the `(username, password)` for a `Fetch.authRequired` handler.

## License

MIT © [ProxyHat](https://proxyhat.com)
