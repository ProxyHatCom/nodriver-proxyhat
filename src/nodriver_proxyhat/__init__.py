"""nodriver-proxyhat — route nodriver (undetected Chrome) through ProxyHat residential proxies."""

from nodriver_proxyhat._auth import enable_proxy_auth
from nodriver_proxyhat._resolve import ProxyHatConfigError, resolve_credentials
from nodriver_proxyhat.proxy import proxyhat_auth, proxyhat_browser, proxyhat_browser_args

__all__ = [
    "ProxyHatConfigError",
    "enable_proxy_auth",
    "proxyhat_auth",
    "proxyhat_browser",
    "proxyhat_browser_args",
    "resolve_credentials",
]
__version__ = "0.1.1"
