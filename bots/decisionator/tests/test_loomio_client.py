"""Tests for Loomio API client."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
import requests

from decisionator.loomio.client import LoomioClient, LoomioClientError
from decisionator.loomio.models import PollType


class TestLoomioClientInit:
    """Tests for LoomioClient initialization."""

    def test_init_with_api_key(self):
        """Initializes with explicit API key."""
        client = LoomioClient(api_key="test-api-key")
        assert client.api_key == "test-api-key"
        assert client.base_url == "http://localhost:3000"

    def test_init_with_custom_url(self):
        """Initializes with custom base URL."""
        client = LoomioClient(api_key="test-key", base_url="https://loomio.example.com")
        assert client.base_url == "https://loomio.example.com"

    def test_init_strips_trailing_slash(self):
        """Strips trailing slash from base URL."""
        client = LoomioClient(api_key="test-key", base_url="https://loomio.example.com/")
        assert client.base_url == "https://loomio.example.com"

    def test_init_from_env_var(self):
        """Initializes from environment variable."""
        with patch.dict("os.environ", {"LOOMIO_API_KEY": "env-api-key"}):
            client = LoomioClient()
            assert client.api_key == "env-api-key"

    def test_init_raises_without_api_key(self):
        """Raises error when API key not provided."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(LoomioClientError, match="LOOMIO_API_KEY"):
                LoomioClient()


class TestLoomioClientRequest:
    """Tests for HTTP request handling."""

    @pytest.fixture
    def client(self):
        return LoomioClient(api_key="test-key")

    def test_request_success(self, client):
        """Makes successful API request."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": "test"}
            mock_response.content = b'{"data": "test"}'
            mock_request.return_value = mock_response

            result = client._get("test/endpoint")

            assert result == {"data": "test"}
            mock_request.assert_called_once()
            call_kwargs = mock_request.call_args.kwargs
            assert call_kwargs["params"]["api_key"] == "test-key"

    def test_request_http_error(self, client):
        """Raises LoomioClientError on HTTP error."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"error": "Not found"}
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=mock_response
            )
            mock_request.return_value = mock_response

            with pytest.raises(LoomioClientError, match="Not found"):
                client._get("test/endpoint")

    def test_request_network_error(self, client):
        """Raises LoomioClientError on network error."""
        with patch.object(client.session, "request") as mock_request:
            mock_request.side_effect = requests.exceptions.ConnectionError("Connection failed")

            with pytest.raises(LoomioClientError, match="Network error"):
                client._get("test/endpoint")


class TestLoomioClientUsers:
    """Tests for user operations."""

    @pytest.fixture
    def client(self):
        return LoomioClient(api_key="test-key")

    def test_create_user(self, client, mock_loomio_user_response):
        """Creates a new Loomio user."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_user_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            user = client.create_user("Test User", "test@example.com")

            assert user.id == 12345
            assert user.name == "Test User"
            assert user.email == "test@example.com"

    def test_lookup_user_found(self, client, mock_loomio_user_response):
        """Returns user when found."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_user_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            user = client.lookup_user("testuser")

            assert user is not None
            assert user.id == 12345

    def test_lookup_user_not_found(self, client):
        """Returns None when user not found."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"error": "User not found"}
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=mock_response
            )
            mock_request.return_value = mock_response

            user = client.lookup_user("nonexistent")

            assert user is None

    def test_update_user_name(self, client, mock_loomio_user_response):
        """Updates user display name."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_user_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            result = client.update_user_name("testuser", "New Name")

            assert result is True
            # First call is lookup, second is patch
            assert mock_request.call_count == 2


class TestLoomioClientGroups:
    """Tests for group operations."""

    @pytest.fixture
    def client(self):
        return LoomioClient(api_key="test-key")

    def test_create_group(self, client, mock_loomio_group_response):
        """Creates a new group."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_group_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            group = client.create_group("Test Group", "A test group")

            assert group.id == 67890
            assert group.name == "Test Group"

    def test_get_group_found(self, client, mock_loomio_group_response):
        """Returns group when found."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_group_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            group = client.get_group(67890)

            assert group is not None
            assert group.id == 67890

    def test_get_group_not_found(self, client):
        """Returns None when group not found."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"error": "Not found"}
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=mock_response
            )
            mock_request.return_value = mock_response

            group = client.get_group(99999)

            assert group is None

    def test_get_group_members(self, client, mock_loomio_user_response):
        """Returns group members."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_user_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            members = client.get_group_members(67890)

            assert len(members) == 1
            assert members[0].id == 12345

    def test_add_member_to_group(self, client):
        """Adds user to group."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.content = b'{}'
            mock_request.return_value = mock_response

            result = client.add_member_to_group(67890, 12345)

            assert result is True

    def test_invite_to_group(self, client):
        """Invites users to group by email."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.content = b'{}'
            mock_request.return_value = mock_response

            result = client.invite_to_group(67890, ["test@example.com"])

            assert result is True


class TestLoomioClientPolls:
    """Tests for poll operations."""

    @pytest.fixture
    def client(self):
        return LoomioClient(api_key="test-key")

    def test_create_poll(self, client, mock_loomio_poll_response):
        """Creates a new poll."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_poll_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            poll = client.create_poll(
                title="Test Poll",
                poll_type=PollType.PROPOSAL,
                group_id=67890,
                details="This is a test poll",
            )

            assert poll.id == 11111
            assert poll.title == "Test Poll"

    def test_get_poll_found(self, client, mock_loomio_poll_response):
        """Returns poll when found."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_poll_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            poll = client.get_poll(11111)

            assert poll is not None
            assert poll.id == 11111

    def test_get_poll_not_found(self, client):
        """Returns None when poll not found."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"error": "Not found"}
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=mock_response
            )
            mock_request.return_value = mock_response

            poll = client.get_poll(99999)

            assert poll is None

    def test_list_polls(self, client, mock_loomio_poll_response):
        """Lists polls for a group."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_poll_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            polls = client.list_polls(67890)

            assert len(polls) == 1
            assert polls[0].id == 11111

    def test_close_poll(self, client):
        """Closes a poll early."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.content = b'{}'
            mock_request.return_value = mock_response

            result = client.close_poll(11111)

            assert result is True

    def test_reopen_poll(self, client):
        """Reopens a closed poll."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.content = b'{}'
            mock_request.return_value = mock_response

            result = client.reopen_poll(11111)

            assert result is True

    def test_extend_poll(self, client, mock_loomio_poll_response):
        """Extends poll deadline."""
        poll_data = mock_loomio_poll_response["polls"][0].copy()
        # Use replace to get UTC offset format, then convert to Z suffix
        closing_dt = datetime.now(timezone.utc) + timedelta(days=1)
        poll_data["closing_at"] = closing_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {"polls": [poll_data]}
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            result = client.extend_poll(11111, additional_hours=24)

            assert result is True

    def test_set_outcome(self, client):
        """Sets poll outcome."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.content = b'{}'
            mock_request.return_value = mock_response

            result = client.set_outcome(11111, "The motion passes!")

            assert result is True

    def test_get_non_voters(self, client, mock_loomio_user_response):
        """Gets non-voters for a poll."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_user_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            users = client.get_non_voters(11111)

            assert len(users) == 1


class TestLoomioClientVoting:
    """Tests for voting (stance) operations."""

    @pytest.fixture
    def client(self):
        return LoomioClient(api_key="test-key")

    def test_cast_vote(self, client, mock_loomio_stance_response):
        """Casts a vote on a poll."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_stance_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            vote = client.cast_vote(
                poll_id=11111,
                choice="agree",
                user_id=12345,
                reason="I agree with this",
            )

            assert vote.poll_id == 11111
            assert vote.participant_id == 12345

    def test_cast_ranked_vote(self, client, mock_loomio_stance_response):
        """Casts a ranked choice vote."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_stance_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            vote = client.cast_ranked_vote(
                poll_id=11111,
                rankings={"option_a": 1, "option_b": 2},
                user_id=12345,
            )

            assert vote.poll_id == 11111
            assert vote.rankings == {"option_a": 1, "option_b": 2}

    def test_cast_meeting_vote(self, client, mock_loomio_stance_response):
        """Casts a meeting poll vote."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_stance_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            vote = client.cast_meeting_vote(
                poll_id=11111,
                available_times=["2025-01-15T10:00", "2025-01-15T14:00"],
                user_id=12345,
            )

            assert vote.poll_id == 11111

    def test_remove_vote(self, client):
        """Removes a vote."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.content = b'{}'
            mock_request.return_value = mock_response

            result = client.remove_vote(stance_id=22222, participant_id=12345)

            assert result is True

    def test_get_stances(self, client, mock_loomio_stance_response):
        """Gets all votes for a poll."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_loomio_stance_response
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            votes = client.get_stances(11111)

            assert len(votes) == 1
            assert votes[0].id == 22222


class TestLoomioClientComments:
    """Tests for comment operations."""

    @pytest.fixture
    def client(self):
        return LoomioClient(api_key="test-key")

    def test_add_comment(self, client):
        """Adds a comment to a poll."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {"comments": [{"id": 33333}]}
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            comment = client.add_comment(
                body="This is a comment",
                user_id=12345,
                poll_id=11111,
            )

            assert comment.id == 33333
            assert comment.body == "This is a comment"

    def test_get_comments(self, client):
        """Gets comments for a poll."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "comments": [
                    {
                        "id": 33333,
                        "body": "Test comment",
                        "author_id": 12345,
                        "poll_id": 11111,
                        "created_at": "2025-01-10T10:00:00Z",
                    }
                ],
                "users": [{"id": 12345, "name": "Test User"}],
            }
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            comments = client.get_comments(poll_id=11111)

            assert len(comments) == 1
            assert comments[0].body == "Test comment"
            assert comments[0].author_name == "Test User"


class TestLoomioClientTasks:
    """Tests for task operations."""

    @pytest.fixture
    def client(self):
        return LoomioClient(api_key="test-key")

    def test_get_group_tasks(self, client):
        """Gets tasks for a group."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "tasks": [
                    {
                        "id": 44444,
                        "name": "Test Task",
                        "done": False,
                        "author_id": 12345,
                        "assignee_ids": [12345],
                    }
                ]
            }
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            tasks = client.get_group_tasks(67890)

            assert len(tasks) == 1
            assert tasks[0].name == "Test Task"

    def test_create_task(self, client):
        """Creates a new task."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {"tasks": [{"id": 44444}]}
            mock_response.content = b'test'
            mock_request.return_value = mock_response

            task = client.create_task(
                group_id=67890,
                name="New Task",
                author_id=12345,
            )

            assert task.id == 44444
            assert task.name == "New Task"

    def test_update_task(self, client):
        """Updates a task."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.content = b'{}'
            mock_request.return_value = mock_response

            result = client.update_task(44444, done=True)

            assert result is True

    def test_delete_task(self, client):
        """Deletes a task."""
        with patch.object(client.session, "request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.content = b'{}'
            mock_request.return_value = mock_response

            result = client.delete_task(44444)

            assert result is True


class TestLoomioClientDateParsing:
    """Tests for datetime parsing."""

    @pytest.fixture
    def client(self):
        return LoomioClient(api_key="test-key")

    def test_parse_datetime_with_z(self, client):
        """Parses datetime with Z timezone."""
        result = client._parse_datetime("2025-01-15T12:00:00Z")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_parse_datetime_with_offset(self, client):
        """Parses datetime with offset timezone."""
        result = client._parse_datetime("2025-01-15T12:00:00+00:00")
        assert result is not None
        assert result.year == 2025

    def test_parse_datetime_none(self, client):
        """Returns None for None input."""
        result = client._parse_datetime(None)
        assert result is None

    def test_parse_datetime_invalid(self, client):
        """Returns None for invalid datetime."""
        result = client._parse_datetime("not-a-date")
        assert result is None
