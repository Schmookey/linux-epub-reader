#!/usr/bin/env python3
"""Adapt the pinned MIT-licensed dbus-next 0.2.3 for bundled Python 3.15.

Python 3.15 removed typing.no_type_check_decorator.  The upstream dbus-next
0.2.3 service module still imports it, which prevents all MPRIS startup.
Patch only the *bundled wheel* after extraction, not Python's stdlib or the
user's host installation.  Fail closed if the upstream layout changes.
"""
import sys
from pathlib import Path

ORIGINAL = "from typing import no_type_check_decorator, Dict, List, Any"
PATCHED = """from typing import no_type_check, Dict, List, Any

# Python 3.15 removed typing.no_type_check_decorator.
# This local compatibility wrapper preserves its historical behaviour.
def no_type_check_decorator(decorator):
    @wraps(decorator)
    def wrapped_decorator(*args, **kwargs):
        return no_type_check(decorator(*args, **kwargs))
    return wrapped_decorator
"""


def patch_dbus_next_service(path):
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    if PATCHED in source:
        return False  # Safe if a build step is retried.
    if source.count(ORIGINAL) != 1 or "from functools import wraps" not in source:
        raise RuntimeError(
            "Unexpected dbus-next service.py: review the compatibility patch"
        )
    updated = source.replace(ORIGINAL, PATCHED, 1)
    compile(updated, str(target), "exec")
    target.write_text(updated, encoding="utf-8")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_dbus_next.py PATH-TO-dbus_next/service.py")
    did_patch = patch_dbus_next_service(sys.argv[1])
    print("dbus-next Python 3.15 compatibility " + ("patched" if did_patch else "already applied"))
