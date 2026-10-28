"""
Atlas-Quant: Autonomous Multi-Agent Algorithmic Trading Research & Execution Engine.
"""

import sys
import types
import uuid as _stdlib_uuid

# Resilient stdlib uuid fallback if compiled extension is blocked by OS Application Control policies
if "uuid_utils" not in sys.modules:
    try:
        import uuid_utils
    except ImportError:
        mod = types.ModuleType("uuid_utils")
        mod.UUID = _stdlib_uuid.UUID
        mod.uuid1 = _stdlib_uuid.uuid1
        mod.uuid3 = _stdlib_uuid.uuid3
        mod.uuid4 = _stdlib_uuid.uuid4
        mod.uuid5 = _stdlib_uuid.uuid5
        mod.uuid6 = getattr(_stdlib_uuid, "uuid6", _stdlib_uuid.uuid1)
        mod.uuid7 = getattr(_stdlib_uuid, "uuid7", _stdlib_uuid.uuid4)
        mod.uuid8 = getattr(_stdlib_uuid, "uuid8", _stdlib_uuid.uuid4)
        mod._uuid4_int = lambda: _stdlib_uuid.uuid4().int
        mod._uuid7_int = lambda timestamp=None, nanos=None: getattr(_stdlib_uuid, "uuid7", _stdlib_uuid.uuid4)().int
        mod.SafeUUID = _stdlib_uuid.SafeUUID
        mod.getnode = _stdlib_uuid.getnode
        mod.NIL = _stdlib_uuid.UUID("00000000-0000-0000-0000-000000000000")
        mod.MAX = _stdlib_uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        mod.NAMESPACE_DNS = _stdlib_uuid.NAMESPACE_DNS
        mod.NAMESPACE_OID = _stdlib_uuid.NAMESPACE_OID
        mod.NAMESPACE_URL = _stdlib_uuid.NAMESPACE_URL
        mod.NAMESPACE_X500 = _stdlib_uuid.NAMESPACE_X500
        mod.RESERVED_FUTURE = _stdlib_uuid.RESERVED_FUTURE
        mod.RESERVED_MICROSOFT = _stdlib_uuid.RESERVED_MICROSOFT
        mod.RESERVED_NCS = _stdlib_uuid.RESERVED_NCS
        mod.RFC_4122 = _stdlib_uuid.RFC_4122
        mod.__version__ = "0.10.0"
        mod.reseed_rng = lambda: None
        sys.modules["uuid_utils"] = mod

        compat_mod = types.ModuleType("uuid_utils.compat")
        compat_mod.uuid7 = mod.uuid7
        compat_mod.uuid4 = mod.uuid4
        compat_mod.uuid1 = mod.uuid1
        compat_mod.uuid3 = mod.uuid3
        compat_mod.uuid5 = mod.uuid5
        compat_mod.uuid6 = mod.uuid6
        compat_mod.uuid8 = mod.uuid8
        compat_mod.UUID = mod.UUID
        sys.modules["uuid_utils.compat"] = compat_mod

__version__ = "1.0.0"

