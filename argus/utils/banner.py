"""
Argus AI Security System — Terminal banner.

Called at startup to display the professional logo.
"""
from __future__ import annotations

ARGUS_BANNER = r"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║        ██████╗ ██████╗   ██████╗ ██╗   ██╗███████╗                           ║
║       ██╔══██╗██╔══██╗ ██╔════╝ ██║   ██║██╔════╝                           ║
║       ███████║██████╔╝ ██║  ███╗██║   ██║███████╗                           ║
║       ██╔══██║██╔══██╗ ██║   ██║██║   ██║╚════██║                           ║
║       ██║  ██║██║  ██║ ╚██████╔╝╚██████╔╝███████║                           ║
║       ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═════╝  ╚═════╝ ╚══════╝                          ║
║                                                                               ║
║          AI-Powered Security System  ·  v0.6.0  ·  Phase 6 Active            ║
║                   Telegram · Discord · Vision · AutoLearn                     ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""


def print_banner() -> None:
    """Print the Argus banner to stdout with color if a terminal supports it."""
    try:
        from rich.console import Console
        from rich.text import Text
        console = Console()
        text = Text(ARGUS_BANNER)
        text.stylize("bold cyan")
        console.print(text)
        console.print()
    except ImportError:
        print(ARGUS_BANNER)
