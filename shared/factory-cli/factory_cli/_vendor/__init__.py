"""Vendored hub packages for standalone `factory-cli` installation."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

_VENDOR_FC_DIR = str(Path(__file__).resolve().parent / "factory_common")

if "factory_common" not in sys.modules:
    _stub = types.ModuleType("factory_common")
    _stub.__path__ = [_VENDOR_FC_DIR]
    _stub.__package__ = "factory_common"
    sys.modules["factory_common"] = _stub
    for _sub in ("client_errors", "http", "logsafe", "secrets", "url_safety"):
        _mod = importlib.import_module(f"factory_common.{_sub}")
        sys.modules[f"factory_cli._vendor.factory_common.{_sub}"] = _mod
