"""CLI commands for Newsinator."""

import os
import click

from signalinator_core import setup_logging, get_logger
from signalinator_core.signal import SignalCLI, SetupWizard

from ..bot import NewsinatorBot

logger = get_logger(__name__)


@click.group()
@click.pass_context
def cli(ctx):
    """Newsinator - Signal bot for Reddit and RSS aggregation."""
    ctx.ensure_object(dict)
    setup_logging()


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True)
@click.option('--config-dir', envvar='SIGNAL_CLI_CONFIG_DIR', default='/signal-cli-config')
@click.option('--voice', is_flag=True)
def setup(phone, config_dir, voice):
    """Set up Signal-CLI registration."""
    wizard = SetupWizard(phone, config_dir)
    if wizard.run_setup(use_voice=voice):
        click.echo("✓ Setup completed!")
    else:
        click.echo("✗ Setup failed.")
        exit(1)


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True)
@click.option('--config-dir', envvar='SIGNAL_CLI_CONFIG_DIR', default='/signal-cli-config')
def status(phone, config_dir):
    """Check Signal-CLI status."""
    wizard = SetupWizard(phone, config_dir)
    wizard.display_status()


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True)
@click.option('--config-dir', envvar='SIGNAL_CLI_CONFIG_DIR', default='/signal-cli-config')
@click.option('--name', default='newsinator')
def link(phone, config_dir, name):
    """Link as secondary device."""
    signal_cli = SignalCLI(phone, config_dir)
    try:
        linking_uri = signal_cli.link_device(name)
        click.echo(f"\nLinking URI:\n{linking_uri}\n")
        click.echo("Scan with Signal app: Settings > Linked Devices > +")
    except Exception as e:
        click.echo(f"✗ Linking failed: {e}")
        exit(1)


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True)
@click.option('--db-path', envvar='DB_PATH', default='/data/newsinator.db')
@click.option('--auto-accept-invites/--no-auto-accept-invites', envvar='AUTO_ACCEPT_GROUP_INVITES', default=True)
def daemon(phone, db_path, auto_accept_invites):
    """Run Newsinator daemon."""
    click.echo("Starting Newsinator daemon...")

    daemon_host = os.getenv("SIGNAL_DAEMON_HOST", "localhost")
    daemon_port = int(os.getenv("SIGNAL_DAEMON_PORT", "8080"))

    click.echo(f"  Phone: {phone}")
    click.echo(f"  Database: {db_path}")
    click.echo(f"  Signal Daemon: {daemon_host}:{daemon_port}")

    try:
        bot = NewsinatorBot(
            phone_number=phone,
            db_path=db_path,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
        )

        click.echo("\n✓ Newsinator initialized")
        click.echo("✓ Commands: /subscribe, /subscribe-top, /subscribe-rss, /list, /help")
        click.echo("✓ Press Ctrl+C to stop.\n")

        bot.run()

    except KeyboardInterrupt:
        click.echo("\n✓ Newsinator stopped.")
    except Exception as e:
        click.echo(f"\n✗ Error: {e}")
        logger.exception("Daemon error")
        exit(1)


if __name__ == "__main__":
    cli()
