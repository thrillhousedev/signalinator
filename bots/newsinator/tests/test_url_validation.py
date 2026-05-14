"""Tests for URL validation (SSRF protection)."""

import pytest
from newsinator.bot import is_safe_url


class TestUrlValidation:
    """Tests for is_safe_url function."""

    # Valid URLs
    def test_valid_https_url(self):
        """Allows valid HTTPS URLs."""
        is_safe, error = is_safe_url("https://example.com/feed.rss")
        assert is_safe is True
        assert error == ""

    def test_valid_http_url(self):
        """Allows valid HTTP URLs."""
        is_safe, error = is_safe_url("http://example.com/feed.rss")
        assert is_safe is True
        assert error == ""

    def test_valid_subdomain(self):
        """Allows subdomains."""
        is_safe, error = is_safe_url("https://rss.example.com/feed")
        assert is_safe is True

    def test_valid_with_port(self):
        """Allows URLs with ports."""
        is_safe, error = is_safe_url("https://example.com:8080/feed.rss")
        assert is_safe is True

    # Invalid schemes
    def test_invalid_scheme_file(self):
        """Rejects file:// URLs."""
        is_safe, error = is_safe_url("file:///etc/passwd")
        assert is_safe is False
        assert "http or https" in error

    def test_invalid_scheme_ftp(self):
        """Rejects ftp:// URLs."""
        is_safe, error = is_safe_url("ftp://example.com/file")
        assert is_safe is False
        assert "http or https" in error

    def test_invalid_scheme_javascript(self):
        """Rejects javascript: URLs."""
        is_safe, error = is_safe_url("javascript:alert(1)")
        assert is_safe is False

    # Localhost blocking
    def test_blocks_localhost(self):
        """Blocks localhost."""
        is_safe, error = is_safe_url("http://localhost/admin")
        assert is_safe is False
        assert "localhost" in error.lower()

    def test_blocks_localhost_localdomain(self):
        """Blocks localhost.localdomain."""
        is_safe, error = is_safe_url("http://localhost.localdomain/admin")
        assert is_safe is False
        assert "localhost" in error.lower()

    # IPv4 blocking
    def test_blocks_127_0_0_1(self):
        """Blocks 127.0.0.1."""
        is_safe, error = is_safe_url("http://127.0.0.1/admin")
        assert is_safe is False
        assert "internal" in error.lower()

    def test_blocks_127_x_x_x(self):
        """Blocks 127.x.x.x range."""
        is_safe, error = is_safe_url("http://127.100.50.1/admin")
        assert is_safe is False

    def test_blocks_10_0_0_0(self):
        """Blocks 10.x.x.x private range."""
        is_safe, error = is_safe_url("http://10.0.0.1/admin")
        assert is_safe is False
        assert "internal" in error.lower()

    def test_blocks_172_16_x_x(self):
        """Blocks 172.16.x.x private range."""
        is_safe, error = is_safe_url("http://172.16.0.1/admin")
        assert is_safe is False

    def test_blocks_172_31_x_x(self):
        """Blocks 172.31.x.x private range."""
        is_safe, error = is_safe_url("http://172.31.255.255/admin")
        assert is_safe is False

    def test_allows_172_32_x_x(self):
        """Allows 172.32.x.x (not private)."""
        is_safe, error = is_safe_url("http://172.32.0.1/feed")
        assert is_safe is True

    def test_blocks_192_168_x_x(self):
        """Blocks 192.168.x.x private range."""
        is_safe, error = is_safe_url("http://192.168.1.1/admin")
        assert is_safe is False

    def test_blocks_169_254_x_x(self):
        """Blocks 169.254.x.x link-local range."""
        is_safe, error = is_safe_url("http://169.254.169.254/metadata")
        assert is_safe is False

    # IPv6 blocking
    def test_blocks_ipv6_loopback(self):
        """Blocks IPv6 loopback."""
        is_safe, error = is_safe_url("http://[::1]/admin")
        assert is_safe is False

    # Internal hostname patterns
    def test_blocks_local_suffix(self):
        """Blocks .local suffix."""
        is_safe, error = is_safe_url("http://server.local/admin")
        assert is_safe is False
        assert "internal" in error.lower()

    def test_blocks_internal_suffix(self):
        """Blocks .internal suffix."""
        is_safe, error = is_safe_url("http://api.internal/admin")
        assert is_safe is False

    def test_blocks_lan_suffix(self):
        """Blocks .lan suffix."""
        is_safe, error = is_safe_url("http://nas.lan/api")
        assert is_safe is False

    def test_blocks_docker_internal(self):
        """Blocks host.docker.internal."""
        is_safe, error = is_safe_url("http://host.docker.internal:8080/api")
        assert is_safe is False

    # No hostname
    def test_rejects_no_hostname(self):
        """Rejects URL without hostname."""
        is_safe, error = is_safe_url("http:///path")
        assert is_safe is False
        assert "hostname" in error.lower()

    # Malformed URLs
    def test_rejects_malformed_url(self):
        """Rejects malformed URLs."""
        is_safe, error = is_safe_url("not a url at all")
        assert is_safe is False

    def test_rejects_empty_string(self):
        """Rejects empty string."""
        is_safe, error = is_safe_url("")
        assert is_safe is False
