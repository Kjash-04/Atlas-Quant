"""
Atlas-Quant lazy stdlib uuid fallback import hook.
Only installs shim when the real uuid_utils compiled extension is missing or unloadable
(e.g., AppLocker, WDAC, missing VC++ runtime, ABI mismatch).
Labels fallback with 0.10.0+stdlib-fallback and IS_STDLIB_FALLBACK = True.
Can be disabled via environment variable ATLAS_UUID_DISABLE_FALLBACK=1.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
import uuid as _stdlib_uuid
from typing import Any, Optional

UUID_STDLIB_FALLBACK_ACTIVE: bool = False


def _fallback_uuid7(
    timestamp: Optional[int] = None, nanos: Optional[int] = None, *args: Any, **kwargs: Any
) -> _stdlib_uuid.UUID:
    if hasattr(_stdlib_uuid, "uuid7"):
        try:
            return _stdlib_uuid.uuid7()
        except TypeError:
            pass
    return _stdlib_uuid.uuid4()


def _fallback_uuid7_int(
    timestamp: Optional[int] = None, nanos: Optional[int] = None, *args: Any, **kwargs: Any
) -> int:
    return _fallback_uuid7(timestamp=timestamp, nanos=nanos).int


def _create_fallback_module(name: str) -> types.ModuleType:
    if name == "uuid_utils":
        mod = types.ModuleType("uuid_utils")
        mod.UUID = _stdlib_uuid.UUID
        mod.uuid1 = _stdlib_uuid.uuid1
        mod.uuid3 = _stdlib_uuid.uuid3
        mod.uuid4 = _stdlib_uuid.uuid4
        mod.uuid5 = _stdlib_uuid.uuid5
        mod.uuid6 = getattr(_stdlib_uuid, "uuid6", _stdlib_uuid.uuid1)
        mod.uuid7 = _fallback_uuid7
        mod.uuid8 = getattr(_stdlib_uuid, "uuid8", _stdlib_uuid.uuid4)
        mod._uuid4_int = lambda: _stdlib_uuid.uuid4().int
        mod._uuid7_int = _fallback_uuid7_int
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
        mod.__version__ = "0.10.0+stdlib-fallback"
        mod.IS_STDLIB_FALLBACK = True
        mod.reseed_rng = lambda: None
        mod.__path__ = []
        return mod
    elif name == "uuid_utils.compat":
        parent = sys.modules.get("uuid_utils")
        if parent is None:
            parent = _create_fallback_module("uuid_utils")
            sys.modules["uuid_utils"] = parent
        compat_mod = types.ModuleType("uuid_utils.compat")
        compat_mod.uuid7 = getattr(parent, "uuid7", _fallback_uuid7)
        compat_mod.uuid4 = parent.uuid4
        compat_mod.uuid1 = parent.uuid1
        compat_mod.uuid3 = parent.uuid3
        compat_mod.uuid5 = parent.uuid5
        compat_mod.uuid6 = getattr(parent, "uuid6", _stdlib_uuid.uuid1)
        compat_mod.uuid8 = getattr(parent, "uuid8", _stdlib_uuid.uuid4)
        compat_mod.UUID = parent.UUID
        return compat_mod
    raise ImportError(f"Unknown fallback module {name}")


class _UUIDCompatLoader(importlib.abc.Loader):
    def create_module(self, spec: importlib.machinery.ModuleSpec) -> types.ModuleType:
        return _create_fallback_module(spec.name)

    def exec_module(self, module: types.ModuleType) -> None:
        pass


class _UUIDCompatFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self, fullname: str, path: Optional[Any] = None, target: Optional[Any] = None
    ) -> Optional[importlib.machinery.ModuleSpec]:
        if os.getenv("ATLAS_UUID_DISABLE_FALLBACK") == "1":
            return None
        if fullname in ("uuid_utils", "uuid_utils.compat"):
            is_package = fullname == "uuid_utils"
            return importlib.machinery.ModuleSpec(
                fullname,
                _UUIDCompatLoader(),
                is_package=is_package,
            )
        return None


def install_uuid_compat() -> bool:
    """
    Installs the fallback meta_path finder when uuid_utils is missing or unloadable
    (e.g., AppLocker, WDAC, missing VC++ runtime, ABI mismatch).
    Can be disabled via environment variable ATLAS_UUID_DISABLE_FALLBACK=1.
    """
    global UUID_STDLIB_FALLBACK_ACTIVE

    if os.getenv("ATLAS_UUID_DISABLE_FALLBACK") == "1":
        UUID_STDLIB_FALLBACK_ACTIVE = False
        return False

    for finder in sys.meta_path:
        if isinstance(finder, _UUIDCompatFinder):
            UUID_STDLIB_FALLBACK_ACTIVE = True
            return True

    # Real import probe: catches ImportError, OSError from failed DLL load
    try:
        import uuid_utils  # noqa: F401
        # Real compiled extension loaded successfully
        UUID_STDLIB_FALLBACK_ACTIVE = False
        return False
    except Exception:
        # A failed import can leave a partial module in sys.modules; clean up both
        sys.modules.pop("uuid_utils", None)
        sys.modules.pop("uuid_utils.compat", None)

    # Insert fallback finder at sys.meta_path[0]
    sys.meta_path.insert(0, _UUIDCompatFinder())
    UUID_STDLIB_FALLBACK_ACTIVE = True
    return True
