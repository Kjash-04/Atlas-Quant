"""
Atlas-Quant: Autonomous Multi-Agent Algorithmic Trading Research & Execution Engine.
"""

from src._uuid_compat import install_uuid_compat

# Install lazy stdlib fallback import hook for uuid_utils if not installed
install_uuid_compat()

__version__ = "1.0.0"
