import logging
from importlib.metadata import entry_points

from qara.plugins.base import BasePlugin

logger = logging.getLogger(__name__)


def load_plugins(enabled: list[str]) -> list[BasePlugin]:
    """Load plugins registered under the `qara.plugins` entry point group."""
    if not enabled:
        return []
    
    eps = {ep.name: ep for ep in entry_points(group="qara.plugins")}
    plugins: list[BasePlugin] = []

    for name in enabled:
        ep = eps.get(name)
        if ep is None:
            logger.warning("Plugin '%s' is enabled in config but not installed", name)
            continue
        try:
            cls = ep.load()
            plugins.append(cls())
            logger.info("Loaded plugin: %s", name)
        except Exception:
            logger.exception("Failed to load plugin '%s'", name)
    
    return plugins