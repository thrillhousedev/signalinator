"""Signal-CLI wrapper for interacting with Signal messenger.

This module provides a subprocess wrapper for signal-cli binary,
used primarily for device linking and setup operations.
For runtime message handling, use SignalSSEClient instead.
"""

import json
import os
import re
import sqlite3
import subprocess
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..logging import get_logger

logger = get_logger(__name__)


class SignalCLIException(Exception):
    """Exception raised for Signal-CLI errors."""
    pass


class SignalCLI:
    """Wrapper for signal-cli command line interface.

    Used for setup/linking and administrative operations.
    For real-time messaging, use SignalSSEClient instead.
    """

    def __init__(self, phone_number: str, config_dir: str = "/signal-cli-config"):
        """Initialize Signal-CLI wrapper.

        Args:
            phone_number: The registered phone number (e.g., +1234567890)
            config_dir: Directory for signal-cli configuration
        """
        self.phone_number = phone_number
        self.config_dir = config_dir
        self.cli_path = "signal-cli"

    def _run_command(
        self,
        args: List[str],
        check_output: bool = True,
        use_account: bool = True,
        json_output: bool = False
    ) -> Optional[str]:
        """Run a signal-cli command.

        Args:
            args: Command arguments
            check_output: Whether to capture and return output
            use_account: Whether to include the account (-a) flag
            json_output: Whether to request JSON output format

        Returns:
            Command output if check_output=True, None otherwise

        Raises:
            SignalCLIException: If command fails
        """
        cmd = [
            self.cli_path,
            "--config", self.config_dir,
        ]

        if use_account:
            cmd.extend(["-a", self.phone_number])

        if json_output:
            cmd.extend(["-o", "json"])

        cmd.extend(args)

        logger.debug(f"Running command: {' '.join(cmd[:5])}...")

        try:
            if check_output:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )
                return result.stdout
            else:
                subprocess.run(cmd, check=True)
                return None
        except subprocess.CalledProcessError as e:
            error_msg = f"Signal-CLI command failed: {e.stderr if e.stderr else str(e)}"
            logger.error(error_msg)
            raise SignalCLIException(error_msg)

    def is_registered(self) -> bool:
        """Check if the phone number is already registered."""
        try:
            self._run_command(["listIdentities"])
            return True
        except SignalCLIException:
            return False

    def register(self, use_voice: bool = False, captcha: str = None) -> str:
        """Register a new phone number with Signal.

        Args:
            use_voice: Use voice call instead of SMS for verification
            captcha: Optional CAPTCHA token from signalcaptchas.org

        Returns:
            Registration message

        Raises:
            SignalCLIException: If registration fails
        """
        args = ["register"]
        if use_voice:
            args.append("--voice")
        if captcha:
            args.extend(["--captcha", captcha])

        output = self._run_command(args)
        logger.info("Registration initiated")
        return output

    def verify(self, verification_code: str) -> str:
        """Verify a phone number with the code received via SMS/voice.

        Args:
            verification_code: 6-digit verification code

        Returns:
            Verification result message

        Raises:
            SignalCLIException: If verification fails
        """
        output = self._run_command(["verify", verification_code])
        logger.info("Phone number verified successfully")
        return output

    def list_groups(self) -> List[Dict[str, Any]]:
        """List all groups the account is a member of.

        Returns:
            List of group dictionaries with id, name, members, admins, description
        """
        output = self._run_command(["listGroups", "-d"])

        groups = []
        if not output:
            return groups

        # Reconstruct multi-line entries (descriptions can contain newlines)
        raw_lines = output.split("\n")
        reconstructed_lines = []
        current_line = ""

        for raw_line in raw_lines:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            if raw_line.startswith("Id:"):
                if current_line:
                    reconstructed_lines.append(current_line)
                current_line = raw_line
            else:
                current_line += " " + raw_line

        if current_line:
            reconstructed_lines.append(current_line)

        # Parse each complete group entry
        for line in reconstructed_lines:
            current_group = {}

            # Extract ID
            id_match = re.search(r'Id:\s*([^\s]+)', line)
            if id_match:
                current_group["id"] = id_match.group(1)

            # Extract Name
            name_match = re.search(r'Name:\s+(.+?)\s+Description:', line)
            if name_match:
                current_group["name"] = name_match.group(1).strip()

            # Extract Description
            desc_match = re.search(r'Description:\s+(.+?)\s+Active:', line)
            if desc_match:
                desc_text = desc_match.group(1).strip()
                if desc_text:
                    current_group["description"] = desc_text

            # Extract Members
            members_match = re.search(r'Members:\s*\[(.*?)\]\s*Pending', line)
            if members_match:
                members_str = members_match.group(1)
                members = []
                for item in [i.strip() for i in members_str.split(',') if i.strip()]:
                    member = {}
                    if item.startswith('+'):
                        member["number"] = item
                    else:
                        member["uuid"] = item
                    members.append(member)
                current_group["members"] = members

            # Extract Admins
            admins_match = re.search(r'Admins:\s*\[(.*?)\]', line)
            if admins_match:
                admins_str = admins_match.group(1)
                admins = []
                for item in [i.strip() for i in admins_str.split(',') if i.strip()]:
                    admin = {}
                    if item.startswith('+'):
                        admin["number"] = item
                    else:
                        admin["uuid"] = item
                    admins.append(admin)
                current_group["admins"] = admins

            if current_group.get("id"):
                groups.append(current_group)

        logger.info(f"Parsed {len(groups)} groups from signal-cli")
        return groups

    def get_group_info(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific group.

        Args:
            group_id: The Signal group ID

        Returns:
            Group information dictionary or None if not found
        """
        groups = self.list_groups()
        for group in groups:
            if group.get("id") == group_id:
                return group
        return None

    def accept_group_invite(self, group_id: str) -> bool:
        """Accept a pending group invite.

        Args:
            group_id: The group ID to accept

        Returns:
            True if successful
        """
        try:
            self._run_command(["updateGroup", "-g", group_id])
            logger.info(f"Accepted group invite")
            return True
        except SignalCLIException as e:
            logger.error(f"Failed to accept group invite: {e}")
            return False

    def send_message(
        self,
        recipient: str,
        message: str,
        group_id: str = None,
        attachment: str = None
    ):
        """Send a message (primarily for testing).

        Args:
            recipient: Phone number or UUID
            message: Message text
            group_id: Group ID if sending to group
            attachment: Path to file to attach (optional)
        """
        args = ["send", "-m", message]

        if attachment:
            args.extend(["--attachment", attachment])

        if group_id:
            args.extend(["-g", group_id])
        else:
            args.append(recipient)

        self._run_command(args, check_output=False)
        logger.info("Message sent")

    def link_device(self, device_name: str = "signalinator") -> str:
        """Link signal-cli as a secondary device to an existing Signal account.

        Args:
            device_name: Name for this linked device

        Returns:
            The linking URI (sgnl://linkdevice?...) to be encoded as QR code

        Raises:
            SignalCLIException: If linking fails to generate URI
        """
        args = ["link", "-n", device_name]

        cmd = [
            self.cli_path,
            "--config", self.config_dir,
        ] + args

        logger.debug(f"Running link command")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )

            output = result.stdout + result.stderr

            for line in output.split("\n"):
                if line.strip().startswith("sgnl://linkdevice"):
                    linking_uri = line.strip()
                    linking_uri = urllib.parse.unquote(linking_uri)
                    logger.info(f"Generated linking URI for device: {device_name}")
                    return linking_uri

            logger.error(f"Could not find linking URI in output")
            raise SignalCLIException("Failed to generate linking URI - not found in output")

        except subprocess.SubprocessError as e:
            logger.error(f"Failed to run link command: {e}")
            raise SignalCLIException(f"Failed to execute link command: {e}")

    def update_profile(
        self,
        name: str = None,
        about: str = None,
        avatar_path: str = None
    ) -> bool:
        """Update the Signal profile.

        Args:
            name: Display name
            about: Profile description/about text
            avatar_path: Path to avatar image file

        Returns:
            True if successful
        """
        args = ["updateProfile"]

        if name:
            args.extend(["--given-name", name])
        if about:
            args.extend(["--about", about])
        if avatar_path:
            args.extend(["--avatar", avatar_path])

        if len(args) == 1:
            logger.warning("No profile updates specified")
            return False

        try:
            self._run_command(args, check_output=False)
            logger.info("Profile updated")
            return True
        except SignalCLIException as e:
            logger.error(f"Failed to update profile: {e}")
            return False

    def set_username(self, username: str) -> Optional[Dict[str, str]]:
        """Set the Signal username for this account.

        Args:
            username: The desired username (e.g., "Conductinator")
                     Signal will assign a discriminator (e.g., ".25")

        Returns:
            Dict with 'username' and 'link' if successful, None otherwise
        """
        args = ["updateAccount", "-u", username]

        try:
            output = self._run_command(args, check_output=True)
            # Parse output like: "Your new username: Conductinator.25 (https://signal.me/#eu/...)"
            if output:
                import re
                match = re.search(r'Your new username: (\S+) \((https://signal\.me/[^)]+)\)', output)
                if match:
                    actual_username = match.group(1)
                    link = match.group(2)
                    logger.info(f"Username set to: {actual_username}")
                    return {"username": actual_username, "link": link}
            logger.info(f"Username command completed but couldn't parse output")
            return {"username": username, "link": None}
        except SignalCLIException as e:
            logger.error(f"Failed to set username: {e}")
            return None
