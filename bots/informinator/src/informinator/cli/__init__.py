"""CLI commands for Informinator."""

import os
import click

from signalinator_core import setup_logging, get_logger
from signalinator_core.signal import SignalCLI, SetupWizard

from ..bot import InforminatorBot

logger = get_logger(__name__)


@click.group()
@click.pass_context
def cli(ctx):
    """Informinator - Signal multi-lobby relay bot."""
    ctx.ensure_object(dict)
    setup_logging()


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True, help='Phone number to register')
@click.option('--config-dir', envvar='SIGNAL_CLI_CONFIG_DIR', default='/signal-cli-config', help='Signal-CLI config directory')
@click.option('--voice', is_flag=True, help='Use voice call instead of SMS')
def setup(phone, config_dir, voice):
    """Set up Signal-CLI registration as primary device."""
    click.echo("Starting Signal-CLI setup...")

    wizard = SetupWizard(phone, config_dir)
    success = wizard.run_setup(use_voice=voice)

    if success:
        click.echo("\n✓ Setup completed successfully!")
    else:
        click.echo("\n✗ Setup failed. Please try again.")
        exit(1)


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True, help='Phone number')
@click.option('--config-dir', envvar='SIGNAL_CLI_CONFIG_DIR', default='/signal-cli-config', help='Signal-CLI config directory')
def status(phone, config_dir):
    """Check Signal-CLI setup status."""
    wizard = SetupWizard(phone, config_dir)
    wizard.display_status()


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True, help='Phone number')
@click.option('--config-dir', envvar='SIGNAL_CLI_CONFIG_DIR', default='/signal-cli-config', help='Signal-CLI config directory')
@click.option('--name', default='informinator', help='Name for this linked device')
def link(phone, config_dir, name):
    """Link signal-cli as a secondary device to your existing Signal account."""
    click.echo("\n" + "="*70)
    click.echo("Signal Device Linking")
    click.echo("="*70)
    click.echo(f"\nPhone Number: {phone}")
    click.echo(f"Device Name: {name}\n")

    click.echo("This will link signal-cli as a SECONDARY device.")
    click.echo("   Your phone will remain your PRIMARY device.\n")

    confirm = input("Continue? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        click.echo("\n✗ Linking cancelled.")
        return

    signal_cli = SignalCLI(phone, config_dir)

    try:
        click.echo("\nGenerating linking URI...")
        linking_uri = signal_cli.link_device(name)

        click.echo("\n" + "="*70)
        click.echo("✓ Linking URI Generated!")
        click.echo("="*70)
        click.echo(f"\n{linking_uri}\n")

        click.echo("="*70)
        click.echo("Next Steps:")
        click.echo("="*70)
        click.echo("\n1. GENERATE QR CODE:")
        click.echo("   - Go to: https://www.qr-code-generator.com/")
        click.echo("   - Select 'URL' type")
        click.echo("   - Paste the URI above")
        click.echo("   - Click 'Create QR Code'\n")

        click.echo("2. SCAN WITH YOUR PHONE:")
        click.echo("   - Open Signal on your iPhone/Android")
        click.echo("   - Tap Settings -> Linked Devices")
        click.echo("   - Tap the '+' button")
        click.echo("   - Scan the QR code you generated\n")

        click.echo("3. VERIFY:")
        click.echo("   After scanning, run:")
        click.echo("   informinator status\n")

        click.echo("="*70)
        click.echo("Note: The linking URI expires after a few minutes!")
        click.echo("="*70 + "\n")

    except Exception as e:
        click.echo(f"\n✗ Linking failed: {e}")
        logger.error(f"Linking failed: {e}")
        exit(1)


@cli.command()
@click.option('--phone', envvar='SIGNAL_PHONE_NUMBER', required=True, help='Phone number')
@click.option('--db-path', envvar='DB_PATH', default='/data/informinator.db', help='Database path')
@click.option('--auto-accept-invites/--no-auto-accept-invites', envvar='AUTO_ACCEPT_GROUP_INVITES', default=True, help='Auto-accept group invites')
def daemon(phone, db_path, auto_accept_invites):
    """Run Informinator daemon with real-time relay."""
    click.echo("Starting Informinator daemon...")

    daemon_host = os.getenv("SIGNAL_DAEMON_HOST", "localhost")
    daemon_port = int(os.getenv("SIGNAL_DAEMON_PORT", "8080"))

    click.echo(f"  Phone: {phone}")
    click.echo(f"  Database: {db_path}")
    click.echo(f"  Signal Daemon: {daemon_host}:{daemon_port}")
    click.echo(f"  Auto-accept invites: {auto_accept_invites}")

    try:
        bot = InforminatorBot(
            phone_number=phone,
            db_path=db_path,
            daemon_host=daemon_host,
            daemon_port=daemon_port,
            auto_accept_invites=auto_accept_invites,
        )

        click.echo("\n✓ Informinator initialized")
        click.echo("✓ Commands: /setup, /status, /anonymous, /greeting, /dm, /help")
        click.echo("✓ Press Ctrl+C to stop.\n")

        bot.run()

    except KeyboardInterrupt:
        click.echo("\n✓ Informinator stopped.")
    except Exception as e:
        click.echo(f"\n✗ Error: {e}")
        logger.exception("Daemon error")
        exit(1)


if __name__ == "__main__":
    cli()
