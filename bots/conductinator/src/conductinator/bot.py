"""Conductinator Signal bot for managing other bot containers."""

import os
from typing import Dict, Optional, Callable

from sqlalchemy import create_engine

from signalinator_core import (
    SignalinatorBot,
    BotCommand,
    CommandContext,
    MessageContext,
    get_logger,
)

from .database import ConductinatorRepository
from .docker import DockerManager

logger = get_logger(__name__)


class ConductinatorBot(SignalinatorBot):
    """Signal bot for managing other Signalinator bot containers.

    Commands (DM only, admin whitelist):
    - /status - Show all bot statuses
    - /start <bot> - Start a stopped bot
    - /stop <bot> - Stop a running bot
    - /restart <bot> - Restart a bot
    - /logs <bot> [lines] - View recent logs
    - /audit [lines] - View recent audit log
    - /health - Check Docker connection health
    """

    def __init__(
        self,
        phone_number: str,
        db_path: str = None,
        docker_socket: str = None,
        daemon_host: str = None,
        daemon_port: int = None,
        auto_accept_invites: bool = False,  # Conductinator doesn't join groups
    ):
        """Initialize Conductinator bot.

        Args:
            phone_number: Bot's Signal phone number
            db_path: Path to SQLite database
            docker_socket: Path to Docker socket (default: /var/run/docker.sock)
            daemon_host: Signal daemon host
            daemon_port: Signal daemon port
            auto_accept_invites: Whether to auto-accept group invites (default: False)
        """
        super().__init__(
            phone_number=phone_number,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
        )

        # Load admin whitelist from environment
        admins_env = os.getenv("CONDUCTINATOR_ADMINS", "")
        self._admin_uuids = set(a.strip() for a in admins_env.split(",") if a.strip())

        if not self._admin_uuids:
            logger.warning("No admins configured! Set CONDUCTINATOR_ADMINS env var.")

        # Database
        db_path = db_path or os.getenv("DB_PATH", "/data/conductinator.db")
        engine = create_engine(f"sqlite:///{db_path}")
        self.repo = ConductinatorRepository(engine)

        # Sync admins from env to database
        for uuid in self._admin_uuids:
            self.repo.add_admin(uuid)

        # Docker manager
        socket = docker_socket or os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")
        try:
            self.docker = DockerManager(socket)
        except Exception as e:
            logger.error(f"Failed to initialize Docker manager: {e}")
            self.docker = None

    @property
    def bot_name(self) -> str:
        return "Conductinator"

    def _get_help_text(self) -> str:
        """Return styled help text grouped by function."""
        return (
            "Conductinator - Bot Management\n\n"
            "📊 Status & Health\n"
            "/status - Show all bot statuses\n"
            "/health - Check Docker connection\n\n"
            "🐳 Container Control\n"
            "/start <bot> - Start a bot\n"
            "/stop <bot> - Stop a bot\n"
            "/restart <bot> - Restart a bot\n\n"
            "📜 Logs & Audit\n"
            "/logs <bot> [n] - View bot logs\n"
            "/daemon-logs <bot> [n] - View daemon logs\n"
            "/audit [n] - View audit log\n\n"
            "🤖 Profile Settings\n"
            "/set-name <name> - Set bot display name\n"
            "/set-about <text> - Set bot description\n"
            "/set-avatar - Set bot avatar (attach image)"
        )

    def get_commands(self) -> Dict[str, BotCommand]:
        return {
            "/help": BotCommand(
                name="/help",
                description="📖 Show this help message",
                handler=lambda ctx: self._get_help_text(),
                dm_only=True,
            ),
            "/status": BotCommand(
                name="/status",
                description="📊 Show all bot statuses",
                handler=self._cmd_status,
                dm_only=True,
            ),
            "/start": BotCommand(
                name="/start",
                description="▶️ Start a stopped bot",
                usage="/start <bot_name>",
                handler=self._cmd_start,
                dm_only=True,
            ),
            "/stop": BotCommand(
                name="/stop",
                description="⏹️ Stop a running bot",
                usage="/stop <bot_name>",
                handler=self._cmd_stop,
                dm_only=True,
            ),
            "/restart": BotCommand(
                name="/restart",
                description="🔄 Restart a bot",
                usage="/restart <bot_name>",
                handler=self._cmd_restart,
                dm_only=True,
            ),
            "/logs": BotCommand(
                name="/logs",
                description="📜 View recent bot logs",
                usage="/logs <bot_name> [lines]",
                handler=self._cmd_logs,
                dm_only=True,
            ),
            "/daemon-logs": BotCommand(
                name="/daemon-logs",
                description="📡 View recent signal daemon logs",
                usage="/daemon-logs <bot_name> [lines]",
                handler=self._cmd_daemon_logs,
                dm_only=True,
            ),
            "/audit": BotCommand(
                name="/audit",
                description="📋 View recent audit log",
                usage="/audit [lines]",
                handler=self._cmd_audit,
                dm_only=True,
            ),
            "/health": BotCommand(
                name="/health",
                description="💓 Check Docker connection health",
                handler=self._cmd_health,
                dm_only=True,
            ),
        }

    def _is_admin(self, context: CommandContext) -> bool:
        """Check if sender is an authorized admin."""
        sender_uuid = context.message.source_uuid
        # Check both env whitelist and database
        return sender_uuid in self._admin_uuids or self.repo.is_admin(sender_uuid)

    def _require_admin(self, context: CommandContext) -> Optional[str]:
        """Check admin and return error message if not authorized."""
        if not self._is_admin(context):
            return "You're not authorized to use Conductinator commands."
        return None

    def _require_docker(self) -> Optional[str]:
        """Check Docker connection and return error message if not available."""
        if not self.docker:
            return "Docker is not connected. Check the Docker socket configuration."
        return None

    # ==================== Commands ====================

    def _cmd_status(self, context: CommandContext) -> str:
        """Handle /status command."""
        if error := self._require_admin(context):
            return error
        if error := self._require_docker():
            return error

        bots = self.docker.list_bots()

        if not bots:
            return "No Signalinator bots found."

        lines = ["Bot Status:"]
        for bot in bots:
            lines.append(f"{bot.status_emoji} {bot.name}: {bot.status_text}")

        # Log action
        self.repo.log_action(context.source_uuid, "status")

        return "\n".join(lines)

    def _cmd_start(self, context: CommandContext) -> str:
        """Handle /start command."""
        if error := self._require_admin(context):
            return error
        if error := self._require_docker():
            return error

        bot_name = context.args.strip().lower() if context.args else ""
        if not bot_name:
            return "Usage: /start <bot_name>\n\nExample: /start taginator"

        success, message = self.docker.start_bot(bot_name)
        self.repo.log_action(
            context.source_uuid,
            "start",
            target_bot=bot_name,
            success=success,
            details=message,
        )

        return f"\u2705 {message}" if success else f"\u274c {message}"

    def _cmd_stop(self, context: CommandContext) -> str:
        """Handle /stop command."""
        if error := self._require_admin(context):
            return error
        if error := self._require_docker():
            return error

        bot_name = context.args.strip().lower() if context.args else ""
        if not bot_name:
            return "Usage: /stop <bot_name>\n\nExample: /stop taginator"

        # Prevent stopping conductinator itself
        if bot_name == "conductinator":
            return "Cannot stop conductinator from within conductinator. Use Docker directly."

        success, message = self.docker.stop_bot(bot_name)
        self.repo.log_action(
            context.source_uuid,
            "stop",
            target_bot=bot_name,
            success=success,
            details=message,
        )

        return f"\u2705 {message}" if success else f"\u274c {message}"

    def _cmd_restart(self, context: CommandContext) -> str:
        """Handle /restart command."""
        if error := self._require_admin(context):
            return error
        if error := self._require_docker():
            return error

        bot_name = context.args.strip().lower() if context.args else ""
        if not bot_name:
            return "Usage: /restart <bot_name>\n\nExample: /restart taginator"

        success, message = self.docker.restart_bot(bot_name)
        self.repo.log_action(
            context.source_uuid,
            "restart",
            target_bot=bot_name,
            success=success,
            details=message,
        )

        return f"\u2705 {message}" if success else f"\u274c {message}"

    def _cmd_logs(self, context: CommandContext) -> str:
        """Handle /logs command."""
        if error := self._require_admin(context):
            return error
        if error := self._require_docker():
            return error

        args = context.args.strip().split() if context.args else []
        if not args:
            return "Usage: /logs <bot_name> [lines]\n\nExample: /logs taginator 50"

        bot_name = args[0].lower()
        lines = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30

        # Cap at 100 lines to avoid huge messages
        lines = min(lines, 100)

        logs = self.docker.get_logs(bot_name, lines=lines, daemon=False)

        if not logs:
            return f"No logs found for {bot_name}"

        self.repo.log_action(
            context.source_uuid,
            "logs",
            target_bot=bot_name,
            details=f"{lines} lines",
        )

        # Truncate if too long for Signal
        if len(logs) > 4000:
            logs = logs[-4000:]
            logs = "...(truncated)\n" + logs

        return f"Logs for {bot_name} (last {lines} lines):\n\n{logs}"

    def _cmd_daemon_logs(self, context: CommandContext) -> str:
        """Handle /daemon-logs command."""
        if error := self._require_admin(context):
            return error
        if error := self._require_docker():
            return error

        args = context.args.strip().split() if context.args else []
        if not args:
            return "Usage: /daemon-logs <bot_name> [lines]\n\nExample: /daemon-logs taginator 50"

        bot_name = args[0].lower()
        lines = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30
        lines = min(lines, 100)

        logs = self.docker.get_logs(bot_name, lines=lines, daemon=True)

        if not logs:
            return f"No daemon logs found for {bot_name}"

        self.repo.log_action(
            context.source_uuid,
            "daemon-logs",
            target_bot=bot_name,
            details=f"{lines} lines",
        )

        if len(logs) > 4000:
            logs = logs[-4000:]
            logs = "...(truncated)\n" + logs

        return f"Daemon logs for {bot_name} (last {lines} lines):\n\n{logs}"

    def _cmd_audit(self, context: CommandContext) -> str:
        """Handle /audit command."""
        if error := self._require_admin(context):
            return error

        lines = 20
        if context.args and context.args.strip().isdigit():
            lines = min(int(context.args.strip()), 50)

        logs = self.repo.get_recent_logs(limit=lines)

        if not logs:
            return "No audit log entries."

        result = [f"Recent actions (last {len(logs)}):"]
        for log in logs:
            ts = log.timestamp.strftime("%m-%d %H:%M")
            status = "\u2705" if log.success else "\u274c"
            target = f" {log.target_bot}" if log.target_bot else ""
            result.append(f"{status} {ts} {log.action}{target}")

        return "\n".join(result)

    def _cmd_health(self, context: CommandContext) -> str:
        """Handle /health command."""
        if error := self._require_admin(context):
            return error

        if not self.docker:
            return "\u274c Docker not connected"

        health = self.docker.health_check()
        check = "\u2705" if health['docker_connected'] else "\u274c"

        lines = [
            "System Health:",
            f"Docker: {check} connected",
            f"Bots found: {health['bots_found']}",
            f"Bots running: {health['bots_running']}",
        ]

        self.repo.log_action(context.source_uuid, "health")

        return "\n".join(lines)

    # ==================== Message Handlers ====================

    def handle_group_message(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Conductinator doesn't handle group messages."""
        return "Conductinator only works via DM. Send me a direct message with /help."

    def handle_dm(
        self,
        context: MessageContext,
        send_response: Callable[[str], bool],
    ) -> Optional[str]:
        """Handle DM that's not a command."""
        if not self._admin_uuids:
            return "Conductinator is not configured. Set CONDUCTINATOR_ADMINS env var."

        sender_uuid = context.source_uuid
        if sender_uuid not in self._admin_uuids and not self.repo.is_admin(sender_uuid):
            return "You're not authorized to use Conductinator."

        return self._get_help_text()

    def on_group_joined(self, group_id: str, group_name: str) -> Optional[str]:
        """Conductinator shouldn't join groups."""
        return "I'm the Conductinator bot. I only work via direct message. Please message me directly!"
