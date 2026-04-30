"""
Hermes Squad — Team coordination plugin for Hermes Agent.

Provides async mailbox, shared task board, wave-based subagent dispatch,
and a web dashboard with image upload capability.

Entry point: register(ctx) — called by Hermes plugin manager at startup.
"""

import logging

logger = logging.getLogger("hermes_squad")


def register(ctx):
    """
    Entry point for Hermes plugin discovery.
    Called automatically when Hermes starts and discovers this plugin
    via pip entry_points or ~/.hermes/plugins/.
    """
    from hermes_squad.plugin import Plugin

    plugin = Plugin(ctx)
    plugin.register_all()
    logger.info("hermes-squad plugin registered (5 tools, 4 CLI commands)")


__all__ = ["register"]
