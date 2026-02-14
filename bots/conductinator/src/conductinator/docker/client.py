"""Docker container management client."""

import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple

import docker
from docker.errors import NotFound, APIError

from signalinator_core import get_logger

logger = get_logger(__name__)

# Container name pattern for signalinator bots
BOT_CONTAINER_PATTERN = re.compile(r"^(signalinator[-_])?(.*?)[-_]?(bot|app)?[-_]?1?$", re.IGNORECASE)
DAEMON_CONTAINER_PATTERN = re.compile(r"^(signalinator[-_])?(.*?)[-_]?(signal[-_]?daemon|daemon)[-_]?1?$", re.IGNORECASE)


@dataclass
class ContainerInfo:
    """Information about a Docker container."""
    id: str
    name: str
    bot_name: str
    status: str
    health: Optional[str]
    is_daemon: bool
    image: str
    created: str
    ports: Dict[str, Any]


@dataclass
class BotStatus:
    """Status of a bot and its daemon."""
    name: str
    bot_container: Optional[ContainerInfo]
    daemon_container: Optional[ContainerInfo]

    @property
    def is_running(self) -> bool:
        """Check if both bot and daemon are running."""
        bot_ok = self.bot_container and self.bot_container.status == "running"
        daemon_ok = self.daemon_container and self.daemon_container.status == "running"
        return bot_ok and daemon_ok

    @property
    def status_emoji(self) -> str:
        """Get status emoji."""
        if self.is_running:
            return "\u2705"  # green checkmark
        elif self.bot_container or self.daemon_container:
            return "\u26a0\ufe0f"  # warning
        return "\u274c"  # red X

    @property
    def status_text(self) -> str:
        """Get human-readable status."""
        bot_status = self.bot_container.status if self.bot_container else "not found"
        daemon_status = self.daemon_container.status if self.daemon_container else "not found"
        return f"bot: {bot_status}, daemon: {daemon_status}"


class DockerManager:
    """Manages Docker containers for Signalinator bots."""

    # Known bot names (for discovery)
    KNOWN_BOTS = [
        "conductinator",
        "decisionator",
        "informationator",
        "informinator",
        "newsinator",
        "summarizinator",
        "taginator",
    ]

    # Dependencies: bots that require additional services
    # When starting these bots, we also start their dependencies
    BOT_DEPENDENCIES = {
        "decisionator": ["loomio-db", "loomio-redis", "loomio", "loomio-worker"],
    }

    def __init__(self, socket_path: str = None):
        """Initialize Docker manager.

        Args:
            socket_path: Path to Docker socket (default: /var/run/docker.sock)
        """
        try:
            if socket_path:
                self.client = docker.DockerClient(base_url=f"unix://{socket_path}")
            else:
                self.client = docker.from_env()
            logger.info("Docker client connected")
        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            raise

    def _extract_bot_name(self, container_name: str) -> Optional[str]:
        """Extract bot name from container name.

        Handles patterns like:
        - taginator
        - taginator-bot
        - signalinator-taginator-1
        - signalinator_taginator_bot_1
        """
        # Remove common prefixes/suffixes
        name = container_name.lower().strip("/")

        # Check against known bots
        for bot in self.KNOWN_BOTS:
            if bot in name:
                return bot

        return None

    def _is_daemon_container(self, container_name: str) -> bool:
        """Check if container is a signal daemon."""
        name = container_name.lower()
        return "daemon" in name or "signal-cli" in name

    def _get_container_info(self, container) -> Optional[ContainerInfo]:
        """Convert Docker container to ContainerInfo."""
        try:
            name = container.name
            bot_name = self._extract_bot_name(name)

            if not bot_name:
                return None

            # Get health status if available
            health = None
            if hasattr(container, "attrs") and "State" in container.attrs:
                health_data = container.attrs["State"].get("Health", {})
                health = health_data.get("Status")

            # Get port mappings
            ports = {}
            if hasattr(container, "attrs") and "NetworkSettings" in container.attrs:
                ports = container.attrs["NetworkSettings"].get("Ports", {})

            return ContainerInfo(
                id=container.short_id,
                name=name,
                bot_name=bot_name,
                status=container.status,
                health=health,
                is_daemon=self._is_daemon_container(name),
                image=container.image.tags[0] if container.image.tags else "unknown",
                created=container.attrs.get("Created", "unknown")[:19] if hasattr(container, "attrs") else "unknown",
                ports=ports,
            )
        except Exception as e:
            logger.error(f"Error getting container info: {e}")
            return None

    def list_bots(self) -> List[BotStatus]:
        """List all Signalinator bots and their status.

        Returns:
            List of BotStatus objects
        """
        try:
            containers = self.client.containers.list(all=True)

            # Group containers by bot name
            bots: Dict[str, BotStatus] = {}

            for container in containers:
                info = self._get_container_info(container)
                if not info:
                    continue

                if info.bot_name not in bots:
                    bots[info.bot_name] = BotStatus(
                        name=info.bot_name,
                        bot_container=None,
                        daemon_container=None,
                    )

                if info.is_daemon:
                    bots[info.bot_name].daemon_container = info
                else:
                    bots[info.bot_name].bot_container = info

            # Sort by name
            return sorted(bots.values(), key=lambda b: b.name)

        except Exception as e:
            logger.error(f"Error listing bots: {e}")
            return []

    def get_bot_status(self, bot_name: str) -> Optional[BotStatus]:
        """Get status of a specific bot.

        Args:
            bot_name: Name of the bot (e.g., "taginator")

        Returns:
            BotStatus or None if not found
        """
        bots = self.list_bots()
        for bot in bots:
            if bot.name.lower() == bot_name.lower():
                return bot
        return None

    def _find_containers_for_bot(self, bot_name: str) -> tuple:
        """Find bot and daemon containers for a bot.

        Returns:
            Tuple of (bot_container, daemon_container)
        """
        bot_container = None
        daemon_container = None

        try:
            containers = self.client.containers.list(all=True)
            for container in containers:
                info = self._get_container_info(container)
                if info and info.bot_name.lower() == bot_name.lower():
                    if info.is_daemon:
                        daemon_container = container
                    else:
                        bot_container = container
        except Exception as e:
            logger.error(f"Error finding containers: {e}")

        return bot_container, daemon_container

    def _find_container_by_name(self, name_pattern: str) -> Optional[Any]:
        """Find a container by name pattern.

        Args:
            name_pattern: Part of container name to match (e.g., "loomio-db")

        Returns:
            Container object or None
        """
        try:
            containers = self.client.containers.list(all=True)
            for container in containers:
                if name_pattern in container.name.lower():
                    return container
        except Exception as e:
            logger.error(f"Error finding container {name_pattern}: {e}")
        return None

    def _start_dependencies(self, bot_name: str) -> Tuple[bool, str]:
        """Start dependency containers for a bot.

        Args:
            bot_name: Name of the bot

        Returns:
            Tuple of (success, message)
        """
        dependencies = self.BOT_DEPENDENCIES.get(bot_name.lower(), [])
        if not dependencies:
            return True, ""

        started = []
        for dep_name in dependencies:
            container = self._find_container_by_name(dep_name)
            if container:
                if container.status != "running":
                    try:
                        container.start()
                        started.append(dep_name)
                        logger.info(f"Started dependency {dep_name} for {bot_name}")
                    except APIError as e:
                        logger.error(f"Failed to start dependency {dep_name}: {e}")
                        return False, f"Failed to start dependency {dep_name}: {e}"
            else:
                logger.warning(f"Dependency container {dep_name} not found")

        if started:
            return True, f"Started dependencies: {', '.join(started)}"
        return True, ""

    def _stop_dependencies(self, bot_name: str) -> Tuple[bool, str]:
        """Stop dependency containers for a bot.

        Args:
            bot_name: Name of the bot

        Returns:
            Tuple of (success, message)
        """
        dependencies = self.BOT_DEPENDENCIES.get(bot_name.lower(), [])
        if not dependencies:
            return True, ""

        stopped = []
        # Stop in reverse order (worker, app, then DBs)
        for dep_name in reversed(dependencies):
            container = self._find_container_by_name(dep_name)
            if container:
                if container.status == "running":
                    try:
                        container.stop(timeout=10)
                        stopped.append(dep_name)
                        logger.info(f"Stopped dependency {dep_name} for {bot_name}")
                    except APIError as e:
                        logger.error(f"Failed to stop dependency {dep_name}: {e}")
                        return False, f"Failed to stop dependency {dep_name}: {e}"

        if stopped:
            return True, f"Stopped dependencies: {', '.join(stopped)}"
        return True, ""

    def start_bot(self, bot_name: str) -> tuple:
        """Start a bot (daemon first, then bot, including dependencies).

        Args:
            bot_name: Name of the bot

        Returns:
            Tuple of (success: bool, message: str)
        """
        bot_container, daemon_container = self._find_containers_for_bot(bot_name)

        if not bot_container and not daemon_container:
            return False, f"No containers found for bot: {bot_name}"

        try:
            # Start dependencies first (e.g., Loomio stack for decisionator)
            dep_success, dep_msg = self._start_dependencies(bot_name)
            if not dep_success:
                return False, dep_msg

            # Start daemon first
            if daemon_container:
                if daemon_container.status != "running":
                    daemon_container.start()
                    logger.info(f"Started daemon for {bot_name}")

            # Then start bot
            if bot_container:
                if bot_container.status != "running":
                    bot_container.start()
                    logger.info(f"Started bot {bot_name}")

            msg = f"Started {bot_name}"
            if dep_msg:
                msg += f" ({dep_msg})"
            return True, msg

        except APIError as e:
            logger.error(f"Docker API error starting {bot_name}: {e}")
            return False, f"Failed to start {bot_name}: {e}"

    def stop_bot(self, bot_name: str) -> tuple:
        """Stop a bot (bot first, then daemon, including dependencies).

        Args:
            bot_name: Name of the bot

        Returns:
            Tuple of (success: bool, message: str)
        """
        bot_container, daemon_container = self._find_containers_for_bot(bot_name)

        if not bot_container and not daemon_container:
            return False, f"No containers found for bot: {bot_name}"

        try:
            # Stop bot first
            if bot_container:
                if bot_container.status == "running":
                    bot_container.stop(timeout=10)
                    logger.info(f"Stopped bot {bot_name}")

            # Then stop daemon
            if daemon_container:
                if daemon_container.status == "running":
                    daemon_container.stop(timeout=10)
                    logger.info(f"Stopped daemon for {bot_name}")

            # Stop dependencies last (e.g., Loomio stack for decisionator)
            dep_success, dep_msg = self._stop_dependencies(bot_name)
            if not dep_success:
                return False, dep_msg

            msg = f"Stopped {bot_name}"
            if dep_msg:
                msg += f" ({dep_msg})"
            return True, msg

        except APIError as e:
            logger.error(f"Docker API error stopping {bot_name}: {e}")
            return False, f"Failed to stop {bot_name}: {e}"

    def restart_bot(self, bot_name: str) -> tuple:
        """Restart a bot.

        Args:
            bot_name: Name of the bot

        Returns:
            Tuple of (success: bool, message: str)
        """
        bot_container, daemon_container = self._find_containers_for_bot(bot_name)

        if not bot_container and not daemon_container:
            return False, f"No containers found for bot: {bot_name}"

        try:
            # Restart dependencies first
            dependencies = self.BOT_DEPENDENCIES.get(bot_name.lower(), [])
            for dep_name in dependencies:
                container = self._find_container_by_name(dep_name)
                if container:
                    container.restart(timeout=10)
                    logger.info(f"Restarted dependency {dep_name} for {bot_name}")

            # Restart daemon first
            if daemon_container:
                daemon_container.restart(timeout=10)
                logger.info(f"Restarted daemon for {bot_name}")

            # Then restart bot
            if bot_container:
                bot_container.restart(timeout=10)
                logger.info(f"Restarted bot {bot_name}")

            return True, f"Restarted {bot_name}"

        except APIError as e:
            logger.error(f"Docker API error restarting {bot_name}: {e}")
            return False, f"Failed to restart {bot_name}: {e}"

    def get_logs(self, bot_name: str, lines: int = 50, daemon: bool = False) -> Optional[str]:
        """Get recent logs from a bot container.

        Args:
            bot_name: Name of the bot
            lines: Number of lines to retrieve
            daemon: If True, get daemon logs instead of bot logs

        Returns:
            Log output string or None if not found
        """
        bot_container, daemon_container = self._find_containers_for_bot(bot_name)

        container = daemon_container if daemon else bot_container
        if not container:
            return None

        try:
            logs = container.logs(tail=lines, timestamps=True).decode("utf-8")
            return logs
        except Exception as e:
            logger.error(f"Error getting logs for {bot_name}: {e}")
            return None

    def health_check(self) -> Dict[str, bool]:
        """Check health of Docker connection and containers.

        Returns:
            Dict with health status
        """
        result = {
            "docker_connected": False,
            "bots_found": 0,
            "bots_running": 0,
        }

        try:
            self.client.ping()
            result["docker_connected"] = True

            bots = self.list_bots()
            result["bots_found"] = len(bots)
            result["bots_running"] = sum(1 for b in bots if b.is_running)

        except Exception as e:
            logger.error(f"Health check failed: {e}")

        return result
