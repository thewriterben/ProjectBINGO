"""What this node would tell you if you asked it whether it should be trusted.

Every hardening increment in this codebase ended with the same shape: an
operator should not have to *infer* whether a safety property holds.
`keys.signing_path_report()` says whether signing is constant-time.
`Store.describe()` says whether writes are isolated. This is the same idea one
level up - one call that answers "is this process in a state where it should be
holding value", and answers it the unflattering way when the answer is no.

The distinction that matters, and the reason there are two verbs:

  * **live**    - the process is running and can serve. Restarting it would not
                  help. This is what a load balancer should poll.
  * **ready**   - the process is in a configuration fit to handle real value.
                  A node can be perfectly live and NOT ready, and conflating the
                  two is how a misconfigured node quietly takes traffic.

`ready` is false if any *blocking* check fails, and every check reports its own
verdict with a reason, so the answer is never a bare boolean an operator has to
go spelunking to interpret. Checks that are merely worth knowing about
(`warn`) do not block - overstating a warning as an outage teaches people to
ignore the endpoint, which is worse than not having it.

Deliberately safe to expose unauthenticated: it reports *properties*, never
values. Whether a token is configured, never the token. Which backend, never
the path's contents. The health endpoint is the most-scraped URL on any service
and it must not become the reconnaissance one.
"""

from __future__ import annotations

import os
import platform
import sys

from . import keys

__all__ = ["report", "Check"]


class Check(dict):
    """A dict on purpose - this gets serialized to JSON and read by humans and
    scrapers alike, and a bespoke class would just need converting back."""

    def __init__(self, name: str, ok: bool, detail: str, *, blocking: bool = True):
        super().__init__(name=name, ok=bool(ok), detail=detail,
                         blocking=bool(blocking),
                         level="ok" if ok else ("fail" if blocking else "warn"))


def report(*, store=None, audit=None, writes_enabled: bool | None = None,
           tls: bool | None = None, extra=None) -> dict:
    """Assemble the readiness report. Never raises: a health check that can
    crash is a health check that reports healthy right up until it doesn't."""
    checks: list[Check] = []

    # -- signing path --
    try:
        sp = keys.signing_path_report()
        audited = bool(sp.get("audited_constant_time_signing"))
        checks.append(Check(
            "signing", audited,
            "audited constant-time signing" if audited else
            "signing is pure-Python and VARIABLE-TIME - it leaks key material "
            "to anyone who can measure. Install `cryptography` or sign in an "
            "HSM before this host holds a key that moves real value.",
            blocking=False))
    except Exception as e:                        # noqa: BLE001
        checks.append(Check("signing", False, f"unavailable: {type(e).__name__}"))

    # -- storage --
    try:
        if store is None:
            checks.append(Check("storage", True, "no store attached to this "
                                                 "process", blocking=False))
        else:
            d = store.describe()
            safe = bool(d.get("cross_process_safe"))
            checks.append(Check(
                "storage", safe,
                f"{d.get('backend')} backend; " +
                ("transactional and cross-process safe" if safe else
                 "NOT cross-process safe - concurrent writers lose updates. "
                 "Set BINGO_STORE=sqlite on any node with more than one writer."),
                blocking=False))
    except Exception as e:                        # noqa: BLE001
        checks.append(Check("storage", False, f"unreadable: {type(e).__name__}"))

    # -- audit chain --
    # this one BLOCKS. A node whose own record of itself does not verify is not
    # a node anyone should be sending value to, whatever else is true of it.
    try:
        if audit is None:
            checks.append(Check("audit", True, "no audit log attached",
                                blocking=False))
        else:
            ok, notes = audit.verify()
            checks.append(Check("audit", ok, notes[-1] if notes else "verified"))
            if audit.errors:
                checks.append(Check(
                    "audit_writes", False,
                    f"{len(audit.errors)} audit write(s) failed - there are "
                    f"gaps in the record: {audit.errors[-1]}"))
    except Exception as e:                        # noqa: BLE001
        checks.append(Check("audit", False, f"unverifiable: {type(e).__name__}"))

    # -- exposure --
    if writes_enabled is not None:
        checks.append(Check(
            "writes", True,
            "enabled (token configured)" if writes_enabled else
            "DISABLED - no $BINGO_API_TOKEN, so money-moving endpoints answer "
            "503. This is the safe default, not a fault.",
            blocking=False))
    if tls is not None:
        checks.append(Check("tls", True, "enabled" if tls else
                            "not terminated here (fine behind a proxy on "
                            "loopback; refused outright off-loopback)",
                            blocking=False))

    for c in (extra or []):
        checks.append(c)

    blocking_failures = [c["name"] for c in checks
                         if c["blocking"] and not c["ok"]]
    warnings = [c["name"] for c in checks if not c["blocking"] and not c["ok"]]
    return {
        "live": True,                    # if this string was produced, it is live
        "ready": not blocking_failures,
        "blocking_failures": blocking_failures,
        "warnings": warnings,
        "checks": checks,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": platform.system(),
        "pid": os.getpid(),
    }
