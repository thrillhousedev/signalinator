"""CLI commands for Taginator."""

import os
import click

from signalinator_core import setup_logging, get_logger

from ..bot import TaginatorBot

logger = get_logger(__name__)


@click.group()
@click.pass_context
def cli(ctx):
    """Taginator - Signal @mention bot."""
    ctx.ensure_object(dict)
    setup_logging()


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True, help='Phone number')
@click.option('--db-path', envvar='DB_PATH', default='/data/taginator.db', help='Database path')
@click.option('--auto-accept-invites/--no-auto-accept-invites', envvar='AUTO_ACCEPT_GROUP_INVITES', default=True, help='Auto-accept group invites')
@click.option('--cooldown', envvar='TAG_COOLDOWN_SECONDS', default=300, type=int, help='Cooldown between /tag uses (seconds)')
def daemon(phone, db_path, auto_accept_invites, cooldown):
    """Run Taginator daemon with real-time command handling."""
    click.echo("Starting Taginator daemon...")

    # Get daemon host/port from env
    daemon_host = os.getenv("SIGNAL_DAEMON_HOST", "localhost")
    daemon_port = int(os.getenv("SIGNAL_DAEMON_PORT", "8080"))

    click.echo(f"  Phone: {phone}")
    click.echo(f"  Database: {db_path}")
    click.echo(f"  Signal Daemon: {daemon_host}:{daemon_port}")
    click.echo(f"  Auto-accept invites: {auto_accept_invites}")
    click.echo(f"  Tag cooldown: {cooldown}s")

    try:
        bot = TaginatorBot(
            phone_number=phone,
            db_path=db_path,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
            cooldown_seconds=cooldown,
        )

        click.echo("\n✓ Taginator initialized")
        click.echo("✓ Commands: /tag, /help, /pause, /unpause")
        click.echo("✓ Press Ctrl+C to stop.\n")

        bot.run()

    except KeyboardInterrupt:
        click.echo("\n✓ Taginator stopped.")
    except Exception as e:
        click.echo(f"\n✗ Error: {e}")
        logger.exception("Daemon error")
        exit(1)


if __name__ == "__main__":
    cli()
