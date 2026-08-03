"""Sentinel — the Promise Integrity watchdog.

Holds the promises external systems make to a person against observed reality:
watch, detect divergence EARLY (while options exist), and remember how each
counterparty keeps its word. See docs/PROMISE-INTEGRITY.md.

The scheduled agent is the driver (it fetches signals with web tools); this
package is the brain — a deterministic classifier so "is this promise off
track?" is tested logic, not improvisation.
"""

__version__ = "0.1.0"
