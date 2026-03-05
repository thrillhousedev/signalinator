#!/usr/bin/env python3
"""Setup commands for signal-cli daemon container."""
import os
import sys

import click

from signalinator_core.signal import SetupWizard, SignalCLI

PHONE = os.environ.get("SIGNAL_PHONE_NUMBER")
CONFIG_DIR = os.environ.get("SIGNAL_CLI_CONFIG_DIR", "/signal-cli-config")


@click.group()
def cli():
    """Signal-CLI setup commands."""
    pass


@cli.command()
@click.option("--voice", is_flag=True, help="Use voice call instead of SMS")
def setup(voice):
    """Register as primary device (new phone number)."""
    if not PHONE:
        click.echo("Error: SIGNAL_PHONE_NUMBER not set")
        sys.exit(1)

    click.echo(f"Setting up Signal account for {PHONE}")
    click.echo(f"Config directory: {CONFIG_DIR}")
    click.echo("")

    wizard = SetupWizard(PHONE, CONFIG_DIR)
    if wizard.run_setup(use_voice=voice):
        click.echo("\n" + "=" * 50)
        click.echo("Setup complete!")
        click.echo("The daemon will automatically detect registration")
        click.echo("and start within 10 seconds.")
        click.echo("=" * 50)
    else:
        click.echo("\nSetup failed.")
        sys.exit(1)


@cli.command()
@click.option("--name", default="signalinator", help="Device name shown in Signal")
def link(name):
    """Link as secondary device (existing Signal account)."""
    if not PHONE:
        click.echo("Error: SIGNAL_PHONE_NUMBER not set")
        sys.exit(1)

    click.echo(f"Linking as secondary device for {PHONE}")
    click.echo(f"Device name: {name}")
    click.echo("")

    signal_cli = SignalCLI(PHONE, CONFIG_DIR)
    try:
        uri = signal_cli.link_device(name)
        click.echo("=" * 50)
        click.echo("Scan this QR code with Signal app:")
        click.echo("  Settings > Linked Devices > +")
        click.echo("")
        click.echo(f"Linking URI:\n{uri}")
        click.echo("=" * 50)
    except Exception as e:
        click.echo(f"Linking failed: {e}")
        sys.exit(1)


@cli.command()
def status():
    """Check registration status."""
    click.echo(f"Checking status for {PHONE or 'unknown'}")
    click.echo(f"Config directory: {CONFIG_DIR}")
    click.echo("")

    wizard = SetupWizard(PHONE or "unknown", CONFIG_DIR)
    wizard.display_status()


@cli.command()
@click.option("--name", required=True, help="Display name for the bot")
@click.option("--about", default=None, help="Profile description/about text")
@click.option("--avatar", default=None, help="Path to avatar image file")
def profile(name, about, avatar):
    """Set the bot's Signal display name, about text, and avatar."""
    if not PHONE:
        click.echo("Error: SIGNAL_PHONE_NUMBER not set")
        sys.exit(1)

    click.echo(f"Updating profile for {PHONE}")

    signal_cli = SignalCLI(PHONE, CONFIG_DIR)
    if signal_cli.update_profile(name=name, about=about, avatar_path=avatar):
        click.echo("=" * 50)
        click.echo("Profile updated successfully!")
        click.echo(f"  Name: {name}")
        if about:
            click.echo(f"  About: {about}")
        if avatar:
            click.echo(f"  Avatar: {avatar}")
        click.echo("=" * 50)
    else:
        click.echo("Failed to update profile.")
        sys.exit(1)


@cli.command()
@click.argument("username")
def username(username):
    """Set the bot's Signal username (e.g., Conductinator).

    The username is the searchable handle others can use to find and
    message this bot. Signal will assign a discriminator (the .XX suffix).
    """
    if not PHONE:
        click.echo("Error: SIGNAL_PHONE_NUMBER not set")
        sys.exit(1)

    click.echo(f"Setting username for {PHONE}")

    signal_cli = SignalCLI(PHONE, CONFIG_DIR)
    result = signal_cli.set_username(username)
    if result:
        click.echo("=" * 50)
        click.echo("Username set successfully!")
        click.echo(f"  Username: {result['username']}")
        if result.get('link'):
            click.echo("")
            click.echo("  Profile link:")
            click.echo(f"  {result['link']}")
        click.echo("=" * 50)
    else:
        click.echo("Failed to set username.")
        click.echo("Note: Signal may reject usernames that are taken or invalid.")
        sys.exit(1)


if __name__ == "__main__":
    cli()
