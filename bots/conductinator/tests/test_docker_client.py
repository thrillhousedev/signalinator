"""Tests for DockerManager."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from conductinator.docker.client import DockerManager, ContainerInfo, BotStatus


class TestContainerInfo:
    """Tests for ContainerInfo dataclass."""

    def test_container_info_fields(self):
        """Test ContainerInfo has all expected fields."""
        info = ContainerInfo(
            id="abc123",
            name="test-container",
            bot_name="testbot",
            status="running",
            health="healthy",
            is_daemon=False,
            image="test:latest",
            created="2024-01-15",
            ports={"8080/tcp": None},
        )

        assert info.id == "abc123"
        assert info.name == "test-container"
        assert info.bot_name == "testbot"
        assert info.status == "running"
        assert info.is_daemon is False


class TestBotStatus:
    """Tests for BotStatus dataclass."""

    def test_is_running_both_running(self, sample_bot_status):
        """Test is_running when both containers are running."""
        assert sample_bot_status.is_running is True

    def test_is_running_bot_stopped(self, sample_bot_status):
        """Test is_running when bot is stopped."""
        sample_bot_status.bot_container.status = "exited"

        assert sample_bot_status.is_running is False

    def test_is_running_daemon_stopped(self, sample_bot_status):
        """Test is_running when daemon is stopped."""
        sample_bot_status.daemon_container.status = "exited"

        assert sample_bot_status.is_running is False

    def test_is_running_no_daemon(self, stopped_bot_status):
        """Test is_running when daemon is missing."""
        assert stopped_bot_status.is_running is False

    def test_status_emoji_running(self, sample_bot_status):
        """Test status emoji for running bot."""
        assert sample_bot_status.status_emoji == "\u2705"  # green check

    def test_status_emoji_partial(self, stopped_bot_status):
        """Test status emoji for partial state."""
        assert stopped_bot_status.status_emoji == "\u26a0\ufe0f"  # warning

    def test_status_emoji_missing(self):
        """Test status emoji when nothing found."""
        status = BotStatus(name="ghost", bot_container=None, daemon_container=None)
        assert status.status_emoji == "\u274c"  # red X

    def test_status_text(self, sample_bot_status):
        """Test status text output."""
        text = sample_bot_status.status_text

        assert "running" in text
        assert "bot:" in text
        assert "daemon:" in text


class TestDockerManagerBotNameExtraction:
    """Tests for bot name extraction from container names."""

    @pytest.fixture
    def manager(self):
        """Create DockerManager with mocked client."""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_docker.return_value = mock_client
            manager = DockerManager()
        return manager

    def test_extract_simple_name(self, manager):
        """Test extracting simple bot name."""
        assert manager._extract_bot_name("taginator") == "taginator"

    def test_extract_with_prefix(self, manager):
        """Test extracting name with signalinator prefix."""
        assert manager._extract_bot_name("signalinator-taginator") == "taginator"

    def test_extract_with_suffix(self, manager):
        """Test extracting name with bot suffix."""
        assert manager._extract_bot_name("taginator-bot") == "taginator"

    def test_extract_compose_format(self, manager):
        """Test extracting from docker compose format."""
        assert manager._extract_bot_name("signalinator-taginator-bot-1") == "taginator"

    def test_extract_underscore_format(self, manager):
        """Test extracting from underscore format."""
        assert manager._extract_bot_name("signalinator_taginator_bot_1") == "taginator"

    def test_extract_unknown_returns_none(self, manager):
        """Test unknown container returns None."""
        assert manager._extract_bot_name("postgres") is None
        assert manager._extract_bot_name("nginx") is None

    def test_all_known_bots(self, manager):
        """Test all known bots are recognized."""
        for bot in manager.KNOWN_BOTS:
            assert manager._extract_bot_name(bot) == bot


class TestDockerManagerDaemonDetection:
    """Tests for daemon container detection."""

    @pytest.fixture
    def manager(self):
        """Create DockerManager with mocked client."""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_docker.return_value = mock_client
            manager = DockerManager()
        return manager

    def test_is_daemon_with_daemon_suffix(self, manager):
        """Test daemon detection with daemon suffix."""
        assert manager._is_daemon_container("taginator-daemon") is True

    def test_is_daemon_with_signal_cli(self, manager):
        """Test daemon detection with signal-cli in name."""
        assert manager._is_daemon_container("taginator-signal-cli") is True

    def test_is_not_daemon(self, manager):
        """Test non-daemon container detection."""
        assert manager._is_daemon_container("taginator-bot") is False
        assert manager._is_daemon_container("taginator") is False


class TestDockerManagerListBots:
    """Tests for listing bots."""

    @pytest.fixture
    def manager_with_containers(self, mock_bot_container, mock_daemon_container):
        """Create DockerManager with mock containers."""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.containers.list.return_value = [mock_bot_container, mock_daemon_container]
            mock_docker.return_value = mock_client
            manager = DockerManager()
        return manager

    def test_list_bots_groups_containers(self, manager_with_containers):
        """Test that bot and daemon are grouped together."""
        bots = manager_with_containers.list_bots()

        assert len(bots) == 1
        assert bots[0].name == "taginator"
        assert bots[0].bot_container is not None
        assert bots[0].daemon_container is not None

    def test_list_bots_sorted_by_name(self):
        """Test that bots are sorted alphabetically."""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()

            # Create containers for multiple bots
            containers = []
            for name in ["taginator", "newsinator", "conductinator"]:
                bot = MagicMock()
                bot.name = f"signalinator-{name}-bot-1"
                bot.short_id = f"{name[:3]}123"
                bot.status = "running"
                bot.attrs = {"State": {}, "NetworkSettings": {"Ports": {}}, "Created": "2024-01-15"}
                bot.image.tags = [f"signalinator/{name}:latest"]
                containers.append(bot)

            mock_client.containers.list.return_value = containers
            mock_docker.return_value = mock_client
            manager = DockerManager()

        bots = manager.list_bots()

        assert [b.name for b in bots] == ["conductinator", "newsinator", "taginator"]


class TestDockerManagerBotOperations:
    """Tests for start/stop/restart operations."""

    @pytest.fixture
    def manager(self, mock_bot_container, mock_daemon_container):
        """Create DockerManager with mock containers."""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.containers.list.return_value = [mock_bot_container, mock_daemon_container]
            mock_docker.return_value = mock_client
            manager = DockerManager()
            manager._mock_bot = mock_bot_container
            manager._mock_daemon = mock_daemon_container
        return manager

    def test_start_bot_success(self, manager):
        """Test starting a bot."""
        manager._mock_bot.status = "exited"
        manager._mock_daemon.status = "exited"

        success, message = manager.start_bot("taginator")

        assert success is True
        assert "Started taginator" in message

    def test_start_bot_not_found(self, manager):
        """Test starting non-existent bot."""
        manager.client.containers.list.return_value = []

        success, message = manager.start_bot("ghostbot")

        assert success is False
        assert "no containers found" in message.lower()

    def test_stop_bot_success(self, manager):
        """Test stopping a bot."""
        success, message = manager.stop_bot("taginator")

        assert success is True
        assert "Stopped taginator" in message

    def test_restart_bot_success(self, manager):
        """Test restarting a bot."""
        success, message = manager.restart_bot("taginator")

        assert success is True
        assert "Restarted taginator" in message


class TestDockerManagerLogs:
    """Tests for log retrieval."""

    @pytest.fixture
    def manager(self, mock_bot_container, mock_daemon_container):
        """Create DockerManager with mock containers."""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.containers.list.return_value = [mock_bot_container, mock_daemon_container]
            mock_docker.return_value = mock_client
            manager = DockerManager()
            manager._mock_bot = mock_bot_container
            manager._mock_daemon = mock_daemon_container
            mock_bot_container.logs.return_value = b"Bot log line 1\nBot log line 2"
            mock_daemon_container.logs.return_value = b"Daemon log line 1"
        return manager

    def test_get_bot_logs(self, manager):
        """Test getting bot logs."""
        logs = manager.get_logs("taginator", lines=50, daemon=False)

        assert logs is not None
        assert "Bot log line" in logs

    def test_get_daemon_logs(self, manager):
        """Test getting daemon logs."""
        logs = manager.get_logs("taginator", lines=50, daemon=True)

        assert logs is not None
        assert "Daemon log line" in logs

    def test_get_logs_not_found(self, manager):
        """Test getting logs for non-existent bot."""
        manager.client.containers.list.return_value = []

        logs = manager.get_logs("ghostbot")

        assert logs is None


class TestDockerManagerHealthCheck:
    """Tests for health check."""

    def test_health_check_success(self):
        """Test health check with working Docker."""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_client.containers.list.return_value = []
            mock_docker.return_value = mock_client
            manager = DockerManager()

        health = manager.health_check()

        assert health["docker_connected"] is True

    def test_health_check_counts_bots(self, sample_bot_status, stopped_bot_status):
        """Test health check counts bots correctly."""
        with patch('docker.from_env') as mock_docker:
            mock_client = MagicMock()
            mock_client.ping.return_value = True
            mock_client.containers.list.return_value = []
            mock_docker.return_value = mock_client
            manager = DockerManager()
            manager.list_bots = MagicMock(return_value=[sample_bot_status, stopped_bot_status])

        health = manager.health_check()

        assert health["bots_found"] == 2
        assert health["bots_running"] == 1  # Only sample_bot_status is running
