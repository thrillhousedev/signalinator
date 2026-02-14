"""Signal integration for Signalinator bots.

Provides SSE streaming for real-time message reception and JSON-RPC for sending.
"""

from .sse_client import SignalSSEClient, SignalMessage
from .cli_wrapper import SignalCLI
from .setup import SetupWizard

__all__ = [
    "SignalSSEClient",
    "SignalMessage",
    "SignalCLI",
    "SetupWizard",
]
