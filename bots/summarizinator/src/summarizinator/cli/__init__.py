"""CLI commands for Summarizinator."""

import os
import click

from signalinator_core import setup_logging, get_logger

from ..bot import SummarizinatorBot

logger = get_logger(__name__)


@click.group()
@click.pass_context
def cli(ctx):
    """Summarizinator - Privacy-focused AI message summarization."""
    ctx.ensure_object(dict)
    setup_logging()


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True)
@click.option('--db-path', envvar='DB_PATH', default='/data/summarizinator.db')
@click.option('--auto-accept-invites/--no-auto-accept-invites', envvar='AUTO_ACCEPT_GROUP_INVITES', default=True)
@click.option('--dm-chat/--no-dm-chat', envvar='DM_CHAT_ENABLED', default=True)
def daemon(phone, db_path, auto_accept_invites, dm_chat):
    """Run Summarizinator daemon."""
    click.echo("Starting Summarizinator daemon...")

    daemon_host = os.getenv("SIGNAL_DAEMON_HOST", "localhost")
    daemon_port = int(os.getenv("SIGNAL_DAEMON_PORT", "8080"))

    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "dolphin-mistral:7b")

    click.echo(f"  Phone: {phone}")
    click.echo(f"  Database: {db_path}")
    click.echo(f"  Signal Daemon: {daemon_host}:{daemon_port}")
    click.echo(f"  Ollama: {ollama_host}")
    click.echo(f"  Model: {ollama_model}")
    click.echo(f"  DM Chat: {'enabled' if dm_chat else 'disabled'}")

    try:
        bot = SummarizinatorBot(
            phone_number=phone,
            db_path=db_path,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
            ollama_host=ollama_host,
            ollama_model=ollama_model,
            dm_chat_enabled=dm_chat,
        )

        click.echo("\nSummarizinator initialized")
        click.echo("Commands: /help, /summary, /opt-out, /retention, /status")
        click.echo("Press Ctrl+C to stop.\n")

        bot.run()

    except KeyboardInterrupt:
        click.echo("\nSummarizinator stopped.")
    except Exception as e:
        click.echo(f"\nError: {e}")
        logger.exception("Daemon error")
        exit(1)


if __name__ == "__main__":
    cli()
