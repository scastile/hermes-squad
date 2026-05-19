"""
Plugin lifecycle — registers tools, CLI commands, and initializes the DB.
"""

import logging
from pathlib import Path

logger = logging.getLogger("hermes_squad.plugin")


class Plugin:
    """Hermes Squad plugin. Registers tools and CLI commands with Hermes."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.hermes_home = Path(getattr(ctx, "hermes_home", "~/.hermes")).expanduser()

    # ── public API ────────────────────────────────────────────────────────

    def register_all(self):
        """Register all tools and CLI commands. Called once at startup."""
        self._register_tools()
        self._register_cli()
        logger.info(
            "hermes-squad: 5 tools + 4 CLI commands registered (DB lazy-initialized)"
        )

    # ── tools ─────────────────────────────────────────────────────────────

    def _register_tools(self):
        from hermes_squad.tools import TOOLS

        for name, (schema, handler) in TOOLS.items():
            self.ctx.register_tool(name, "team", schema, handler)
            logger.debug(f"hermes-squad: registered tool '{name}'")

    # ── CLI ───────────────────────────────────────────────────────────────

    def _register_cli(self):
        from hermes_squad.cli import setup_parser

        self.ctx.register_cli_command(
            name="squad",
            help="Team coordination (setup, status, web, cleanup)",
            setup_fn=setup_parser,
            description="Hermes Squad — multi-agent coordination plugin",
        )
        logger.debug("hermes-squad: registered CLI 'hermes squad'")
