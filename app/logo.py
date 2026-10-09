import base64
import ipaddress
import socket
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


opener = build_opener(NoRedirect)


def load(ref: str) -> bytes:
    if ref.startswith("data:"):
        try:
            raw = base64.b64decode(ref.partition(",")[2], validate=True)
        except ValueError:
            raise ValueError("invalid base64 in data URI")
    else:
        url = urlparse(ref)
        if url.scheme not in ("http", "https") or not url.hostname:
            raise ValueError("must be an http(s) URL or a data URI")
        port = url.port or (443 if url.scheme == "https" else 80)
        for *_, addr in socket.getaddrinfo(url.hostname, port, type=socket.SOCK_STREAM):
            if not ipaddress.ip_address(addr[0].split("%")[0]).is_global:
                raise ValueError("logo host is not a public address")
        with opener.open(Request(ref, headers={"User-Agent": "certgen"}), timeout=5) as resp:
            raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("logo is larger than 2 MB")
    return raw
