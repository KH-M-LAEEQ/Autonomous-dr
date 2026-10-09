"""Provider registry. `Settings.providers` selects which are active.

Returns live singleton instances, not classes instantiated per call -- a
provider (the simulator especially, via `core.faults`) needs continuity of
state across calls, not a fresh instance per request.
"""

from core.config import get_settings
from core.interfaces import CloudProvider
from core.providers.simulated import SimulatedProvider

_INSTANCES: dict[str, CloudProvider] = {
    "simulated": SimulatedProvider(),
}


def get_provider(name: str) -> CloudProvider:
    if name not in _INSTANCES:
        raise KeyError(f"unknown provider {name!r}; registered: {sorted(_INSTANCES)}")
    return _INSTANCES[name]


def enabled_providers() -> list[CloudProvider]:
    """Every provider named in `Settings.providers`, in that order."""
    return [get_provider(name) for name in get_settings().enabled_providers]
