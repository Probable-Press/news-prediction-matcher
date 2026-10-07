"""Real HTTP framing and socket lifetimes, using only local AF_UNIX socketpairs.

The production URL and DNS checks still run. Only the connection factory is
replaced, so http.client owns and releases a real socket and response file.
No TCP/IP connection, TLS override or security-policy change is needed.
"""
import errno
import http.client
import socket
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import safe_fetch as sf

URL = "https://www.bbc.co.uk/news/articles/example"
PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def response_bytes(body, *, framing="length", length=None):
    headers = b"HTTP/1.1 200 OK\r\nConnection: close\r\n"
    if framing == "length":
        size = len(body) if length is None else length
        headers += f"Content-Length: {size}\r\n".encode()
    elif framing == "chunked":
        headers += b"Transfer-Encoding: chunked\r\n"
        body = (f"{len(body):x}\r\n".encode() + body + b"\r\n" if body else b"") + b"0\r\n\r\n"
    return headers + b"\r\n" + body


class SocketLifecycleTests(unittest.TestCase):
    @contextmanager
    def connection(self, wire):
        client, peer = socket.socketpair(socket.AF_UNIX)
        # Keep fixture writes bounded and finite even if a test is changed.
        client.settimeout(1)
        peer.settimeout(1)
        conn = http.client.HTTPConnection("www.bbc.co.uk", port=443)
        conn.sock = client
        try:
            peer.sendall(wire)
            peer.shutdown(socket.SHUT_WR)
            with patch.object(conn, "connect"), \
                 patch.object(sf, "_PinnedHTTPSConnection", return_value=conn), \
                 patch.object(sf.socket, "getaddrinfo", return_value=PUBLIC), \
                 patch.object(sf.socket, "socket", side_effect=AssertionError("network forbidden")):
                yield conn, client
        finally:
            conn.close()
            client.close()
            peer.close()

    def fetch(self, wire, max_bytes):
        with self.connection(wire) as (conn, client):
            try:
                return sf.fetch_bytes(URL, max_bytes=max_bytes)
            finally:
                self.assertIsNone(conn.sock)
                self.assertEqual(client.fileno(), -1)

    def test_fixture_reproduces_final_chunk_closing_socket(self):
        with self.connection(response_bytes(b"abc")) as (conn, client):
            conn.request("GET", "/", headers={"Connection": "close"})
            with conn.getresponse() as response:
                self.assertIsNone(conn.sock)
                self.assertNotEqual(client.fileno(), -1)
                self.assertEqual(response.read1(65536), b"abc")
                self.assertTrue(response.isclosed())
                with self.assertRaises(OSError) as error:
                    client.settimeout(1)
                self.assertEqual(error.exception.errno, errno.EBADF)

    def test_fixed_length_final_chunk(self):
        self.assertEqual(self.fetch(response_bytes(b"abc"), 3), (b"abc", URL))

    def test_fixed_length_multiple_reads(self):
        body = b"x" * 65537
        self.assertEqual(self.fetch(response_bytes(body), len(body)), (body, URL))

    def test_zero_length_response_and_limit(self):
        self.assertEqual(self.fetch(response_bytes(b""), 0), (b"", URL))

    def test_chunked_and_close_delimited_responses(self):
        for framing in ("chunked", "close"):
            for body in (b"", b"abc"):
                with self.subTest(framing=framing, body=body):
                    self.assertEqual(self.fetch(response_bytes(body, framing=framing), len(body)),
                                     (body, URL))

    def test_oversized_responses_fail_closed(self):
        for framing in ("length", "chunked", "close"):
            with self.subTest(framing=framing), self.assertRaises(sf.FetchRejected):
                self.fetch(response_bytes(b"abcd", framing=framing), 3)

    def test_truncated_fixed_length_fails_closed(self):
        with self.assertRaisesRegex(sf.FetchRejected, "Incomplete"):
            self.fetch(response_bytes(b"abc", length=4), 4)

    def test_truncated_chunked_fails_closed(self):
        wire = b"HTTP/1.1 200 OK\r\nConnection: close\r\nTransfer-Encoding: chunked\r\n\r\n4\r\nabc"
        with self.assertRaises(http.client.IncompleteRead):
            self.fetch(wire, 4)

    def test_deadline_after_final_chunk_is_still_enforced(self):
        with self.connection(response_bytes(b"abc")) as (_, client):
            with patch.object(sf.time, "monotonic", side_effect=[0, 0, 0, 0, 31]):
                with self.assertRaisesRegex(TimeoutError, "deadline"):
                    sf.fetch_bytes(URL, max_bytes=3)
            self.assertEqual(client.fileno(), -1)

    def test_read_timeout_still_closes_socket(self):
        # Supply headers but neither a body nor EOF, forcing a real socket read.
        client, peer = socket.socketpair(socket.AF_UNIX)
        conn = http.client.HTTPConnection("www.bbc.co.uk", port=443)
        conn.sock = client
        try:
            peer.sendall(b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 1\r\n\r\n")
            with patch.object(conn, "connect"), \
                 patch.object(sf, "_PinnedHTTPSConnection", return_value=conn), \
                 patch.object(sf.socket, "getaddrinfo", return_value=PUBLIC), \
                 patch.object(sf.socket, "socket", side_effect=AssertionError("network forbidden")), \
                 patch.object(sf, "READ_TIMEOUT", 0.01):
                with self.assertRaises(TimeoutError):
                    sf.fetch_bytes(URL, max_bytes=1)
            self.assertIsNone(conn.sock)
            self.assertEqual(client.fileno(), -1)
        finally:
            conn.close()
            client.close()
            peer.close()


if __name__ == "__main__":
    unittest.main()
