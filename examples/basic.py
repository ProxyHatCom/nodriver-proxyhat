"""Minimal nodriver + ProxyHat example.

    PROXYHAT_API_KEY=ph_xxx python examples/basic.py

nodriver launches an undetected Chrome routed through a US residential IP, pinned
for the whole session (sticky by default) so cookies and fingerprint stay
consistent. Gateway auth is handled over CDP — no extension, no proxy wrapper.
"""

import nodriver as uc

from nodriver_proxyhat import proxyhat_browser


async def main() -> None:
    # api_key defaults to PROXYHAT_API_KEY; auto-selects an active sub-user.
    browser = await proxyhat_browser(country="us", headless=False)

    page = await browser.get("https://httpbin.org/ip")
    print(await page.get_content())

    browser.stop()


if __name__ == "__main__":
    # nodriver ships its own loop helper (asyncio.run never worked reliably for it).
    uc.loop().run_until_complete(main())
