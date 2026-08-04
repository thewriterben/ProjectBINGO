"""Machine RWA, end to end — finance a printer, repay backers from its earnings.

  raise capital by selling shares of a machine's future revenue
  -> the machine earns from PoF-verified jobs
  -> a slice streams pro-rata to backers until repaid, then reverts to the operator

Run:  python -m provenance.machine_rwa_demo   (from v3/)

The closing line is the vision in one integer: strangers financed a teenager's
second printer, and got paid back automatically from what the machine actually,
provably made — no bank, no equity, no personal guarantee.
"""

from __future__ import annotations

from provenance.passport import Actor
from provenance.machine_rwa import MachineShare


def main() -> int:
    op = Actor.create("op", "Operator (bedroom print shop)", "operator", "acct:node:printer-7")
    backers = [
        (Actor.create("rosa", "Rosa", "investor", "acct:rosa"), 40),
        (Actor.create("sam", "Sam", "investor", "acct:sam"), 35),
        (Actor.create("theo", "Theo", "investor", "acct:theo"), 25),
    ]

    # Offer 100 shares at $10 to finance a $1,000 machine; backers take 60% of the
    # machine's revenue until they've been repaid 1.2x ($1,200), then it's the
    # operator's outright.
    ms = MachineShare(machine_id="printer-7", total_shares=100, price_cents=1000,
                      investor_share_bps=6000, repayment_cap_cents=120_000,
                      operator=op, ts="2026-08-04T00:00:00Z")
    for inv, shares in backers:
        ms.buy(inv, shares, ts="t-raise")

    print("Project BINGO — machine RWA / node financing\n")
    print(f"Machine: printer-7   offering {ms.events[0]['hash'][:16]}…")
    print(f"Raised ${ms.capital_raised()/100:,.2f} from {len(backers)} backers "
          f"({ms.sold_shares()}/{ms.total_shares} shares); backers get "
          f"{ms.investor_share_bps/100:.0f}% of revenue until repaid "
          f"${ms.repayment_cap_cents/100:,.2f} (1.2×).")

    # The machine runs. Each figure below is what the printer earned on real,
    # PoF-verified jobs that period (fed from the settlement ledger in practice).
    monthly_revenue = [40_000, 55_000, 60_000, 70_000, 80_000]  # cents/month
    print("\nMonth   revenue   →  backers   operator   (cumulative repaid)")
    for i, rev in enumerate(monthly_revenue, 1):
        d = ms.earn(op, rev, f"month-{i}", ts=f"m{i}")
        repaid_now = ms.fully_repaid()
        just_repaid = repaid_now and (ms.cumulative_paid() - d["to_investors"]) < ms.repayment_cap_cents
        print(f"  {i}    ${rev/100:>7.2f}   →  ${d['to_investors']/100:>6.2f}   "
              f"${d['to_operator']/100:>6.2f}    (${ms.cumulative_paid()/100:,.2f} / "
              f"${ms.repayment_cap_cents/100:,.0f})"
              + ("   ✓ REPAID — machine is now the operator's outright" if just_repaid else ""))

    print("\nBacker returns (pro-rata by shares):")
    ie = ms.investor_earnings()
    names = {"acct:rosa": "Rosa (40 sh)", "acct:sam": "Sam (35 sh)", "acct:theo": "Theo (25 sh)"}
    for acct, cents in sorted(ie.items(), key=lambda kv: -kv[1]):
        print(f"  {names.get(acct, acct):<16} ${cents/100:>7.2f}")

    assert sum(ie.values()) == ms.repayment_cap_cents
    print(f"\n  ✓ ${sum(ie.values())/100:,.2f} returned to backers, to the cent — "
          "exactly the 1.2× cap, then the machine reverts to the operator.")
    print("\nThe integer that is the whole idea: three strangers put up "
          f"${ms.capital_raised()/100:,.0f} for a bedroom print shop's second "
          f"printer and were paid back ${ms.repayment_cap_cents/100:,.0f} from what "
          "the machine provably earned — no bank, no equity, no personal guarantee.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
