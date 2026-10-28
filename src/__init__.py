"""
Atlas-Quant: Autonomous Multi-Agent Algorithmic Trading Research & Execution Engine.
"""

from src._uuid_compat import install_uuid_compat

# Install lazy stdlib fallback import hook for uuid_utils if not installed
install_uuid_compat()

__version__ = "1.0.0"


def __getattr__(name: str):
    if name == "UUID_STDLIB_FALLBACK_ACTIVE":
        from src._uuid_compat import UUID_STDLIB_FALLBACK_ACTIVE
        return UUID_STDLIB_FALLBACK_ACTIVE
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["install_uuid_compat", "UUID_STDLIB_FALLBACK_ACTIVE", "__version__"]
