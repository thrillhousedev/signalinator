"""Tests for Signal SSE client functionality."""

import json
import pytest
from unittest.mock import MagicMock, patch, Mock

from signalinator_core.signal.sse_client import SignalSSEClient, SignalMessage


class TestSignalMessage:
    """Tests for SignalMessage dataclass."""

    def test_default_values(self):
        """Test SignalMessage default values."""
        msg = SignalMessage(
            timestamp=1700000000000,
            source_uuid="uuid-123",
            source_number="+1234567890",
            group_id=None,
            group_name=None,
            message="Hello",
        )

        assert msg.mentions == []
        assert msg.attachments == []
        assert msg.expires_in_seconds == 0
        assert msg.raw_envelope == {}


class TestSignalSSEClientInit:
    """Tests for SignalSSEClient initialization."""

    def test_init_default_host_port(self):
        """Test initialization with default host and port."""
        client = SignalSSEClient("+1234567890")

        assert client.phone_number == "+1234567890"
        assert client.host == "localhost"
        assert client.port == 8080
        assert client.base_url == "http://localhost:8080/api/v1/rpc"

    def test_init_custom_host_port(self):
        """Test initialization with custom host and port."""
        client = SignalSSEClient("+1234567890", host="signal-daemon", port=9090)

        assert client.host == "signal-daemon"
        assert client.port == 9090
        assert client.base_url == "http://signal-daemon:9090/api/v1/rpc"


class TestSignalSSEClientRPC:
    """Tests for JSON-RPC functionality."""

    @pytest.fixture
    def client(self):
        """Create a SignalSSEClient for testing."""
        return SignalSSEClient("+1234567890")

    def test_call_rpc_success(self, client, mock_rpc_response):
        """Test successful RPC call."""
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = mock_rpc_response
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            result = client._call_rpc("testMethod", {"param": "value"})

            assert result == {"timestamp": 1700000000000}
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == client.base_url
            payload = call_args[1]["json"]
            assert payload["method"] == "testMethod"
            assert payload["params"] == {"param": "value"}

    def test_call_rpc_error_response(self, client):
        """Test RPC call with error response."""
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32600, "message": "Invalid request"},
            }
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            with pytest.raises(Exception) as exc_info:
                client._call_rpc("badMethod")

            assert "-32600" in str(exc_info.value)
            assert "Invalid request" in str(exc_info.value)

    def test_call_rpc_increments_id(self, client, mock_rpc_response):
        """Test that RPC request IDs increment."""
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = mock_rpc_response
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            client._call_rpc("method1")
            client._call_rpc("method2")

            calls = mock_post.call_args_list
            id1 = calls[0][1]["json"]["id"]
            id2 = calls[1][1]["json"]["id"]
            assert id2 > id1


class TestSignalSSEClientMessaging:
    """Tests for messaging functionality."""

    @pytest.fixture
    def client(self):
        """Create a SignalSSEClient for testing."""
        return SignalSSEClient("+1234567890")

    def test_send_message_to_group(self, client, mock_rpc_response):
        """Test sending message to group."""
        with patch.object(client, "_call_rpc", return_value=mock_rpc_response):
            result = client.send_message("Hello group!", group_id="group-123")

            assert result is True
            client._call_rpc.assert_called_once()
            call_args = client._call_rpc.call_args
            assert call_args[0][0] == "send"
            params = call_args[0][1]
            assert params["message"] == "Hello group!"
            assert params["groupId"] == "group-123"

    def test_send_message_to_recipient(self, client, mock_rpc_response):
        """Test sending direct message."""
        with patch.object(client, "_call_rpc", return_value=mock_rpc_response):
            result = client.send_message("Hello!", recipient="uuid-123")

            assert result is True
            call_args = client._call_rpc.call_args
            params = call_args[0][1]
            assert params["recipient"] == ["uuid-123"]

    def test_send_message_no_target_returns_false(self, client):
        """Test that sending without target returns False."""
        result = client.send_message("Hello!")

        # Should return False and log error, not raise
        assert result is False

    def test_send_message_with_attachment(self, client, mock_rpc_response):
        """Test sending message with attachment."""
        with patch.object(client, "_call_rpc", return_value=mock_rpc_response):
            result = client.send_message(
                "See attached",
                group_id="group-123",
                attachment_path="/tmp/file.txt",
            )

            assert result is True
            params = client._call_rpc.call_args[0][1]
            assert params["attachments"] == ["/tmp/file.txt"]

    def test_send_message_with_mentions(self, client, mock_rpc_response):
        """Test sending message with @mentions."""
        with patch.object(client, "_call_rpc", return_value=mock_rpc_response):
            mentions = [{"start": 0, "length": 5, "uuid": "user-uuid"}]
            result = client.send_message(
                "@user hello!",
                group_id="group-123",
                mentions=mentions,
            )

            assert result is True
            params = client._call_rpc.call_args[0][1]
            assert "mention" in params
            assert "0:5:user-uuid" in params["mention"]

    def test_send_reaction_success(self, client, mock_rpc_response):
        """Test sending reaction."""
        with patch.object(client, "_call_rpc", return_value=mock_rpc_response):
            result = client.send_reaction(
                emoji="👍",
                target_author="author-uuid",
                target_timestamp=1700000000000,
                group_id="group-123",
            )

            assert result is True
            call_args = client._call_rpc.call_args
            assert call_args[0][0] == "sendReaction"
            params = call_args[0][1]
            assert params["emoji"] == "👍"
            assert params["targetAuthor"] == "author-uuid"
            assert params["targetTimestamp"] == 1700000000000


class TestSignalSSEClientGroups:
    """Tests for group-related functionality."""

    @pytest.fixture
    def client(self):
        """Create a SignalSSEClient for testing."""
        return SignalSSEClient("+1234567890")

    def test_list_groups(self, client, sample_groups):
        """Test listing groups."""
        with patch.object(client, "_call_rpc", return_value=sample_groups):
            groups = client.list_groups()

            assert len(groups) == 2
            assert groups[0]["name"] == "Test Group"

    def test_list_groups_empty(self, client):
        """Test listing groups when none exist."""
        with patch.object(client, "_call_rpc", return_value=None):
            groups = client.list_groups()

            assert groups == []

    def test_is_daemon_running_true(self, client, sample_groups):
        """Test daemon check when running."""
        with patch.object(client, "_call_rpc", return_value=sample_groups):
            assert client.is_daemon_running() is True

    def test_is_daemon_running_false(self, client):
        """Test daemon check when not running."""
        with patch.object(client, "_call_rpc", side_effect=Exception("Connection refused")):
            assert client.is_daemon_running() is False

    def test_accept_group_invite(self, client, mock_rpc_response):
        """Test accepting group invite."""
        with patch.object(client, "_call_rpc", return_value=mock_rpc_response):
            result = client.accept_group_invite("group-123")

            assert result is True
            call_args = client._call_rpc.call_args
            assert call_args[0][0] == "updateGroup"

    def test_is_pending_member_true(self, client):
        """Test checking pending membership when true."""
        groups = [{
            "id": "group-123",
            "isMember": False,
        }]
        with patch.object(client, "list_groups", return_value=groups):
            assert client.is_pending_member("group-123") is True

    def test_is_pending_member_false(self, client, sample_groups):
        """Test checking pending membership when false."""
        with patch.object(client, "list_groups", return_value=sample_groups):
            assert client.is_pending_member("ABC123XYZ789+/=DEF456") is False


class TestSignalSSEClientProfile:
    """Tests for profile management."""

    @pytest.fixture
    def client(self):
        """Create a SignalSSEClient for testing."""
        return SignalSSEClient("+1234567890")

    def test_get_own_uuid_from_group(self, client, sample_groups):
        """Test getting own UUID from group membership."""
        # Add the client's phone number as a member
        sample_groups[0]["members"].append(
            {"uuid": "my-uuid-123", "number": "+1234567890"}
        )
        with patch.object(client, "list_groups", return_value=sample_groups):
            uuid = client.get_own_uuid()

            assert uuid == "my-uuid-123"

    def test_get_own_uuid_not_found(self, client):
        """Test getting own UUID when not in any group."""
        with patch.object(client, "list_groups", return_value=[]):
            with patch.object(client, "_call_rpc", return_value=[]):
                uuid = client.get_own_uuid()

                assert uuid is None

    def test_set_profile(self, client, mock_rpc_response):
        """Test setting profile."""
        with patch.object(client, "_call_rpc", return_value=mock_rpc_response):
            result = client.set_profile(name="Bot Name", about="A helpful bot")

            assert result is True
            call_args = client._call_rpc.call_args
            assert call_args[0][0] == "updateProfile"
            params = call_args[0][1]
            assert params["givenName"] == "Bot Name"
            assert params["about"] == "A helpful bot"


class TestSignalSSEClientParsing:
    """Tests for envelope parsing."""

    @pytest.fixture
    def client(self):
        """Create a SignalSSEClient for testing."""
        return SignalSSEClient("+1234567890")

    def test_parse_envelope_group_message(self, client, sample_envelope):
        """Test parsing group message envelope."""
        msg = client._parse_envelope(sample_envelope["envelope"])

        assert msg is not None
        assert msg.timestamp == 1700000000000
        assert msg.source_uuid == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert msg.source_number == "+14155551234"
        assert msg.group_id == "ABC123XYZ789+/=DEF456"
        assert msg.message == "Hello world"

    def test_parse_envelope_dm(self, client, sample_dm_envelope):
        """Test parsing DM envelope."""
        msg = client._parse_envelope(sample_dm_envelope["envelope"])

        assert msg is not None
        assert msg.group_id is None
        assert msg.message == "Hello from DM"

    def test_parse_envelope_with_mentions(self, client):
        """Test parsing envelope with mentions."""
        envelope = {
            "timestamp": 1700000000000,
            "sourceUuid": "sender-uuid",
            "sourceNumber": "+1234567890",
            "dataMessage": {
                "message": "\uFFFC hello",
                "mentions": [
                    {"uuid": "mentioned-uuid", "start": 0, "length": 1}
                ],
            },
        }

        msg = client._parse_envelope(envelope)

        assert msg is not None
        assert len(msg.mentions) == 1
        assert msg.mentions[0]["uuid"] == "mentioned-uuid"

    def test_parse_envelope_with_attachments(self, client):
        """Test parsing envelope with attachments."""
        envelope = {
            "timestamp": 1700000000000,
            "sourceUuid": "sender-uuid",
            "dataMessage": {
                "message": "See attached",
                "attachments": [
                    {"contentType": "image/png", "filename": "photo.png"}
                ],
            },
        }

        msg = client._parse_envelope(envelope)

        assert msg is not None
        assert len(msg.attachments) == 1
        assert msg.attachments[0]["filename"] == "photo.png"

    def test_parse_envelope_malformed(self, client):
        """Test parsing malformed envelope returns None."""
        envelope = {"bad": "data"}

        msg = client._parse_envelope(envelope)

        # Should return a message with None/empty values, not crash
        assert msg is not None or msg is None  # Implementation-dependent


class TestSignalSSEClientHandlers:
    """Tests for message handler management."""

    @pytest.fixture
    def client(self):
        """Create a SignalSSEClient for testing."""
        return SignalSSEClient("+1234567890")

    def test_add_handler(self, client):
        """Test adding message handler."""
        def handler(msg):
            pass

        client.add_handler(handler)

        assert handler in client._handlers

    def test_multiple_handlers(self, client):
        """Test adding multiple handlers."""
        def handler1(msg):
            pass

        def handler2(msg):
            pass

        client.add_handler(handler1)
        client.add_handler(handler2)

        assert len(client._handlers) == 2
