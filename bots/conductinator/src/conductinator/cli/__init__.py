"""CLI commands for Conductinator."""

import os
import click

from signalinator_core import setup_logging, get_logger
from signalinator_core.signal import SignalCLI, SetupWizard

from ..bot import ConductinatorBot

logger = get_logger(__name__)


@click.group()
@click.pass_context
def cli(ctx):
    """Conductinator - Signal bot for managing other bots"""
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
        click.echo("Setup completed!")
    else:
        click.echo("Setup failed.")
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
@click.option('--name', default='conductinator')
def link(phone, config_dir, name):
    """Link as secondary device."""
    signal_cli = SignalCLI(phone, config_dir)
    try:
        linking_uri = signal_cli.link_device(name)
        click.echo(f"\nLinking URI:\n{linking_uri}\n")
        click.echo("Scan with Signal app: Settings > Linked Devices > +")
    except Exception as e:
        click.echo(f"Linking failed: {e}")
        exit(1)


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True)
@click.option('--db-path', envvar='DB_PATH', default='/data/conductinator.db')
@click.option('--docker-socket', envvar='DOCKER_SOCKET', default='/var/run/docker.sock')
def daemon(phone, db_path, docker_socket):
    """Run Conductinator daemon."""
    click.echo("Starting Conductinator daemon...")

    daemon_host = os.getenv("SIGNAL_DAEMON_HOST", "localhost")
    daemon_port = int(os.getenv("SIGNAL_DAEMON_PORT", "8080"))

    click.echo(f"  Phone: {phone}")
    click.echo(f"  Database: {db_path}")
    click.echo(f"  Docker socket: {docker_socket}")
    click.echo(f"  Signal Daemon: {daemon_host}:{daemon_port}")

    # Check for admin configuration
    admins = os.getenv("CONDUCTINATOR_ADMINS", "")
    if not admins:
        click.echo("\nWARNING: No admins configured!")
        click.echo("Set CONDUCTINATOR_ADMINS env var with comma-separated UUIDs.")

    try:
        bot = ConductinatorBot(
            phone_number=phone,
            db_path=db_path,
            docker_socket=docker_socket,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
        )

        click.echo("\nConductinator initialized")
        click.echo("Press Ctrl+C to stop.\n")

        bot.run()

    except KeyboardInterrupt:
        click.echo("\nConductinator stopped.")
    except Exception as e:
        click.echo(f"\nError: {e}")
        logger.exception("Daemon error")
        exit(1)


@cli.command()
@click.option('--docker-socket', envvar='DOCKER_SOCKET', default='/var/run/docker.sock')
def check_docker(docker_socket):
    """Check Docker connection and list bots."""
    from ..docker import DockerManager

    click.echo(f"Checking Docker connection: {docker_socket}")

    try:
        docker = DockerManager(docker_socket)
        health = docker.health_check()

        if health["docker_connected"]:
            click.echo("Docker: Connected")
            click.echo(f"Bots found: {health['bots_found']}")
            click.echo(f"Bots running: {health['bots_running']}")

            bots = docker.list_bots()
            if bots:
                click.echo("\nBot Status:")
                for bot in bots:
                    click.echo(f"  {bot.status_emoji} {bot.name}: {bot.status_text}")
        else:
            click.echo("Docker: Not connected")
            exit(1)

    except Exception as e:
        click.echo(f"Docker check failed: {e}")
        exit(1)


if __name__ == "__main__":
    cli()
