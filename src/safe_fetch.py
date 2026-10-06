"""Small, direct HTTPS fetcher for trusted news hosts and untrusted URLs.

No proxies, cookies, credentials, automatic redirects or second DNS lookup.
TLS still authenticates the original hostname when connecting to a pinned IP.
"""

import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

SOURCE_HOSTS = (
    frozenset({"news.web.nhk", "www3.nhk.or.jp"}),
    frozenset({"news.yahoo.co.jp"}),
    frozenset({"feeds.bbci.co.uk", "www.bbc.co.uk", "www.bbc.com"}),
)
ALLOWED_HOSTS = frozenset().union(*SOURCE_HOSTS)
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 10
TOTAL_TIMEOUT = 30
MAX_REDIRECTS = 5
MAX_FEED_BYTES = 2 * 1024 * 1024
MAX_ARTICLE_BYTES = 4 * 1024 * 1024


class FetchRejected(ValueError):
    """The target or response violates the collector's safety policy."""


def validate_url(url, allowed_hosts=ALLOWED_HOSTS):
    if not isinstance(url, str) or len(url) > 8192:
        raise FetchRejected("Invalid URL")
    if any(ord(c) <= 32 or ord(c) == 127 for c in url) or "\\" in url:
        raise FetchRejected("URL contains whitespace or control characters")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in allowed_hosts
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443)):
        raise FetchRejected("Only approved HTTPS news hosts on port 443 are allowed")
    return parsed


def _public_addresses(host):
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise FetchRejected("No addresses")
    # Reject the entire DNS answer if any address is non-public. In particular,
    # do not let fallback behavior select a private answer from a mixed set.
    for family, _, _, _, address in addresses:
        ip = ipaddress.ip_address(address[0])
        if (family not in (socket.AF_INET, socket.AF_INET6)
                or not ip.is_global or ip.is_multicast or ip.is_reserved
                or (ip.version == 6 and (ip.ipv4_mapped or ip.sixtofour
                                         or ip.teredo))):
            raise FetchRejected("DNS target is not a public unicast address")
    return addresses


def _remaining(deadline, limit):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Fetch deadline exceeded")
    return min(limit, remaining)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, addresses, deadline):
        super().__init__(host, timeout=CONNECT_TIMEOUT,
                         context=ssl.create_default_context())
        self._addresses = addresses
        self._deadline = deadline

    def connect(self):
        last_error = None
        for family, socktype, proto, _, address in self._addresses:
            raw = socket.socket(family, socktype, proto)
            try:
                raw.settimeout(_remaining(self._deadline, CONNECT_TIMEOUT))
                # address is the numeric sockaddr already validated above.
                # Never pass the hostname to create_connection / getaddrinfo.
                raw.connect(address)
                raw.settimeout(_remaining(self._deadline, CONNECT_TIMEOUT))
                self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
                return
            except (OSError, TimeoutError) as exc:
                raw.close()
                last_error = exc
        raise last_error or FetchRejected("No usable address")


def fetch_bytes(url, *, max_bytes, headers=None):
    """Return (bounded identity-encoded bytes, final URL), or fail closed.

    Per-operation socket timeouts and a cooperative total deadline bound reads
    and redirects; OS DNS resolution and HTTP header/trailer parsing can still overrun
    that deadline. The surrounding job must retain its wall-clock timeout.
    """
    first = validate_url(url)
    hosts = next(group for group in SOURCE_HOSTS if first.hostname in group)
    deadline = time.monotonic() + TOTAL_TIMEOUT
    for hop in range(MAX_REDIRECTS + 1):
        parsed = validate_url(url, hosts)
        addresses = _public_addresses(parsed.hostname)
        _remaining(deadline, CONNECT_TIMEOUT)
        conn = _PinnedHTTPSConnection(parsed.hostname, addresses, deadline)
        try:
            conn.connect()
            conn.sock.settimeout(_remaining(deadline, READ_TIMEOUT))
            path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            request_headers = dict(headers or {})
            request_headers.update({"Accept-Encoding": "identity", "Connection": "close"})
            conn.request("GET", path, headers=request_headers)
            transport = conn.sock
            with conn.getresponse() as response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    if not location or hop == MAX_REDIRECTS:
                        raise FetchRejected("Missing redirect target or too many redirects")
                    url = urljoin(url, location)
                    validate_url(url, hosts)
                    continue
                if response.status != 200:
                    raise FetchRejected(f"HTTP status {response.status}")
                if response.getheader("Content-Encoding", "identity").lower() != "identity":
                    raise FetchRejected("Compressed responses are not accepted")
                length = response.getheader("Content-Length")
                if length is not None and (not length.isdecimal() or int(length) > max_bytes):
                    raise FetchRejected("Invalid or oversized Content-Length")
                body = bytearray()
                while True:
                    transport.settimeout(_remaining(deadline, READ_TIMEOUT))
                    chunk = response.read1(min(65536, max_bytes + 1 - len(body)))
                    _remaining(deadline, READ_TIMEOUT)
                    if not chunk:
                        return bytes(body), url
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise FetchRejected("Response exceeds byte limit")
        finally:
            conn.close()
    raise FetchRejected("Too many redirects")
