"""Offline tests: no external, loopback or private network connections."""
import io
import socket
import ssl
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import safe_fetch as sf
import main

URL = "https://www.bbc.co.uk/news/articles/example"
PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class Response:
    def __init__(self, body=b"ok", status=200, headers=None):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = headers or {}
        self.closed = False

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read1(self, size):
        return self.body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.dns = patch.object(sf.socket, "getaddrinfo", return_value=PUBLIC).start()
        # Fail all real socket creation, including accidental localhost tests.
        patch.object(sf.socket, "socket", side_effect=AssertionError("network forbidden")).start()
        self.factory = patch.object(sf, "_PinnedHTTPSConnection").start()
        self.addCleanup(patch.stopall)

    def responses(self, *responses):
        connections = []
        for response in responses:
            conn = Mock()
            conn.getresponse.return_value = response
            connections.append(conn)
        self.factory.side_effect = connections
        return connections

    def test_normal_bytes_and_request_authority(self):
        conn, = self.responses(Response(b"news"))
        self.assertEqual(sf.fetch_bytes(URL, max_bytes=4), (b"news", URL))
        self.assertEqual(self.factory.call_args.args[:2], ("www.bbc.co.uk", PUBLIC))
        self.assertEqual(conn.request.call_args.args, ("GET", "/news/articles/example"))
        self.assertEqual(conn.request.call_args.kwargs["headers"]["Accept-Encoding"], "identity")
        conn.close.assert_called_once()

    def test_bad_urls_rejected_before_dns(self):
        for url in ["http://www.bbc.co.uk/a", "file:///etc/passwd", "ftp://www.bbc.co.uk/a",
                    "https://127.0.0.1/a", "https://www.bbc.co.uk.evil.test/a",
                    "https://evil.test/?www.bbc.co.uk", "https://u:p@www.bbc.co.uk/a",
                    "https://www.bbc.co.uk:8443/a", "https://www.bbc.co.uk/a\r\nx:y",
                    "https://www.bbc.co.uk\\@evil.test/a"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                sf.fetch_bytes(url, max_bytes=100)
        self.dns.assert_not_called()
        self.factory.assert_not_called()

    def test_all_nonpublic_and_mixed_answers_rejected(self):
        for ip in ["127.0.0.1", "10.0.0.1", "169.254.169.254", "100.64.0.1",
                   "0.0.0.0", "224.0.0.1", "::1", "fc00::1", "fe80::1",
                   "::ffff:127.0.0.1", "2002:7f00:1::", "64:ff9b:1::1"]:
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            self.dns.return_value = PUBLIC + [(family, socket.SOCK_STREAM, 6, "", (ip, 443))]
            with self.subTest(ip=ip), self.assertRaises(sf.FetchRejected):
                sf.fetch_bytes(URL, max_bytes=100)
        self.factory.assert_not_called()

    def test_valid_bbc_redirect_and_relative_redirect(self):
        responses = [Response(status=302, headers={"Location": "/news/other"}),
                     Response(status=301, headers={"Location": "https://www.bbc.com/news/other"}),
                     Response(b"article")]
        self.responses(*responses)
        self.assertEqual(sf.fetch_bytes(URL, max_bytes=100),
                         (b"article", "https://www.bbc.com/news/other"))
        self.assertEqual(self.dns.call_count, 3)
        self.assertTrue(all(r.closed for r in responses))

    def test_redirect_target_validation(self):
        for target in ["http://www.bbc.co.uk/a", "https://evil.test/a",
                       "https://127.0.0.1/", "https://news.yahoo.co.jp/a"]:
            self.factory.reset_mock()
            self.responses(Response(status=302, headers={"Location": target}))
            with self.subTest(target=target), self.assertRaises(sf.FetchRejected):
                sf.fetch_bytes(URL, max_bytes=100)
            self.assertEqual(self.factory.call_count, 1)

    def test_redirect_dns_is_checked_again(self):
        self.dns.side_effect = [PUBLIC, [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))]]
        self.responses(Response(status=302, headers={"Location": "/other"}))
        with self.assertRaises(sf.FetchRejected):
            sf.fetch_bytes(URL, max_bytes=100)
        self.assertEqual(self.factory.call_count, 1)

    def test_redirect_loop_is_finite(self):
        self.responses(*(Response(status=302, headers={"Location": URL}) for _ in range(6)))
        with self.assertRaises(sf.FetchRejected):
            sf.fetch_bytes(URL, max_bytes=100)
        self.assertEqual(self.factory.call_count, 6)

    def test_byte_limit_without_or_with_lying_length(self):
        for headers in [{}, {"Content-Length": "1"}, {"Content-Length": "1000"}]:
            self.responses(Response(b"12345", headers=headers))
            with self.subTest(headers=headers), self.assertRaises(sf.FetchRejected):
                sf.fetch_bytes(URL, max_bytes=4)

    def test_compression_and_error_status_rejected(self):
        for response in [Response(headers={"Content-Encoding": "gzip"}), Response(status=404)]:
            self.responses(response)
            with self.assertRaises(sf.FetchRejected):
                sf.fetch_bytes(URL, max_bytes=100)

    def test_total_deadline_checked_after_dns(self):
        with patch.object(sf.time, "monotonic", side_effect=[0, 31]):
            with self.assertRaises(TimeoutError):
                sf.fetch_bytes(URL, max_bytes=100)
        self.factory.assert_not_called()

    def test_source_hosts_and_https_feeds(self):
        for url in main.NEWS_FEEDS.values():
            sf.validate_url(url)
        for host in ["news.web.nhk", "news.yahoo.co.jp", "www.bbc.co.uk", "www.bbc.com"]:
            sf.validate_url("https://" + host + "/news")

    def test_article_fixture_and_yahoo_pickup(self):
        body = "This is a sufficiently long article paragraph for extraction."
        pickup = b'<a href="/articles/example">Read</a>'
        self.responses(Response(pickup), Response(("<article><p>" + body + "</p></article>").encode()))
        self.assertEqual(main.scrape_body("https://news.yahoo.co.jp/pickup/example"), body)

    def test_feed_and_article_share_bounded_fetcher(self):
        rss = b"<rss><channel><item><title>News</title><link>https://www.bbc.co.uk/news/a</link></item></channel></rss>"
        article = b"<article><p>This is a sufficiently long BBC article paragraph.</p></article>"
        self.responses(Response(rss), Response(article))
        with patch.dict(main.NEWS_FEEDS, {"BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml"}, clear=True):
            result = main.fetch(1)
        self.assertEqual(result[0]["title"], "News")
        self.assertIn("BBC article", result[0]["body"])

    def test_read_timeout_closes_connection(self):
        response = Response()
        response.read1 = Mock(side_effect=TimeoutError("read timeout"))
        conn, = self.responses(response)
        with self.assertRaises(TimeoutError):
            sf.fetch_bytes(URL, max_bytes=100)
        self.assertTrue(response.closed)
        conn.close.assert_called_once()

    def test_malicious_yahoo_followup_falls_back(self):
        pickup = '<a href="http://127.0.0.1/articles/x">記事全文を読む</a>'
        self.responses(Response(pickup.encode()))
        self.assertEqual(main.scrape_body("https://news.yahoo.co.jp/pickup/example"), "")
        self.assertEqual(self.factory.call_count, 1)


class PinningTests(unittest.TestCase):
    def test_numeric_connect_sni_and_certificate_validation(self):
        context = ssl.create_default_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        fake_context = Mock(wraps=context)
        fake_context.wrap_socket = Mock(return_value=Mock())
        raw = Mock()
        with patch.object(sf.socket, "socket", return_value=raw), \
             patch.object(sf.socket, "getaddrinfo", side_effect=AssertionError("second DNS lookup")), \
             patch.object(sf.ssl, "create_default_context", return_value=fake_context):
            conn = sf._PinnedHTTPSConnection("www.bbc.co.uk", PUBLIC, sf.time.monotonic() + 30)
            conn.connect()
        raw.connect.assert_called_once_with(("93.184.216.34", 443))
        fake_context.wrap_socket.assert_called_once_with(raw, server_hostname="www.bbc.co.uk")

    def test_real_http_parser_chunked_close_and_host_header(self):
        # Exercise http.client framing without connecting any socket. Real
        # Connection: close makes HTTPConnection.sock None after getresponse.
        wire = (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
                b"Connection: close\r\n\r\n4\r\nnews\r\n0\r\n\r\n")
        transport = Mock()
        transport.makefile.return_value = io.BytesIO(wire)
        context = Mock()
        context.wrap_socket.return_value = transport
        with patch.object(sf.socket, "getaddrinfo", return_value=PUBLIC), \
             patch.object(sf.socket, "socket", return_value=Mock()), \
             patch.object(sf.ssl, "create_default_context", return_value=context):
            self.assertEqual(sf.fetch_bytes(URL, max_bytes=4), (b"news", URL))
        sent = b"".join(call.args[0] for call in transport.sendall.call_args_list)
        self.assertIn(b"Host: www.bbc.co.uk\r\n", sent)
        self.assertNotIn(b"Host: 93.184.216.34", sent)

    def test_chunked_oversize_uses_actual_bytes(self):
        wire = (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
                b"Connection: close\r\n\r\n5\r\n12345\r\n0\r\n\r\n")
        transport = Mock()
        transport.makefile.return_value = io.BytesIO(wire)
        context = Mock()
        context.wrap_socket.return_value = transport
        with patch.object(sf.socket, "getaddrinfo", return_value=PUBLIC), \
             patch.object(sf.socket, "socket", return_value=Mock()), \
             patch.object(sf.ssl, "create_default_context", return_value=context):
            with self.assertRaises(sf.FetchRejected):
                sf.fetch_bytes(URL, max_bytes=4)

    def test_tls_mismatch_is_not_bypassed(self):
        context = Mock()
        context.wrap_socket.side_effect = ssl.SSLCertVerificationError("hostname mismatch")
        raw = Mock()
        with patch.object(sf.socket, "socket", return_value=raw), \
             patch.object(sf.ssl, "create_default_context", return_value=context):
            conn = sf._PinnedHTTPSConnection("www.bbc.co.uk", PUBLIC, sf.time.monotonic() + 30)
            with self.assertRaises(ssl.SSLCertVerificationError):
                conn.connect()
        raw.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
