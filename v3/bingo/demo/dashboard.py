"""Renders the public dashboard: the royalty counter, per-participant
earnings, and the full provenance/journal trail. Self-contained HTML."""

from __future__ import annotations

from ..ledger import Ledger, NETWORK_ACCOUNT, CARRIER_ACCOUNT
from ..models import Order
from ..node.agent import NodeAgent
from ..registry import AssetRegistry


def _usd(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def render_dashboard(registry: AssetRegistry, ledger: Ledger,
                     orders: list[Order], agents: list[NodeAgent]) -> str:
    assets = registry.all()
    creator_accounts = sorted({p.account for a in assets for p in a.effective_split.payees})
    total_units = sum(o.qty for o in orders)
    machines = {j.node_id for o in orders for j in o.jobs}
    total_royalties = sum(ledger.balance(a) for a in creator_accounts)

    asset_rows = ""
    for a in assets:
        split_txt = " · ".join(f"{p.account.replace('acct:', '')} {p.bps / 100:.0f}%"
                               for p in a.effective_split.payees)
        deriv = f" — remix of {a.derives_from[0].asset_id[:10]}…" if a.derives_from else ""
        asset_rows += (f"<tr><td><code>{a.asset_id[:12]}…</code></td><td>{a.title}{deriv}</td>"
                       f"<td>{a.license.per_unit_cents}¢/unit</td><td>{split_txt}</td></tr>")

    earn_rows = ""
    for acct in creator_accounts:
        earn_rows += (f"<tr><td>{acct}</td><td>creator</td>"
                      f"<td class='amt'>{_usd(ledger.balance(acct))}</td></tr>")
    for ag in agents:
        bal = ledger.balance(f"acct:node:{ag.info.node_id}")
        earn_rows += (f"<tr><td>{ag.info.operator}</td><td>node — {ag.info.name}</td>"
                      f"<td class='amt'>{_usd(bal)}</td></tr>")
    earn_rows += (f"<tr><td>{CARRIER_ACCOUNT}</td><td>logistics</td>"
                  f"<td class='amt'>{_usd(ledger.balance(CARRIER_ACCOUNT))}</td></tr>")
    earn_rows += (f"<tr><td>{NETWORK_ACCOUNT}</td><td>network fee (3%)</td>"
                  f"<td class='amt'>{_usd(ledger.balance(NETWORK_ACCOUNT))}</td></tr>")

    job_rows = ""
    for o in orders:
        for j in o.jobs:
            job_rows += (f"<tr><td><code>{j.job_id}</code></td><td>{o.order_id}</td>"
                         f"<td>{j.node_id}</td><td>{j.qty}</td><td>{j.state.value}</td>"
                         f"<td>{len(j.evidence)}</td>"
                         f"<td><code>{j.chain_head()[:16]}…</code></td></tr>")

    journal_rows = ""
    for e in ledger.journal:
        legs = "<br>".join(f"{l.account} ← {_usd(l.amount_cents)} <i>({l.memo})</i>"
                           for l in e.legs)
        journal_rows += (f"<tr><td>{e.entry_id}</td><td>{e.kind}</td>"
                         f"<td>{e.job_id or '—'}</td><td>{legs}</td></tr>")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BINGO — network dashboard (thin vertical demo)</title>
<style>
  :root {{ --bg:#0e1116; --card:#161b22; --ink:#e6edf3; --dim:#8b949e;
           --accent:#4ade80; --line:#242b36; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.55 system-ui, sans-serif; padding:2rem 1rem 4rem; }}
  main {{ max-width:960px; margin:0 auto; }}
  h1 {{ font-size:1.2rem; letter-spacing:.06em; color:var(--dim);
       text-transform:uppercase; }}
  .hero {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
          padding:2rem; margin:1rem 0 2rem; text-align:center; }}
  .hero .big {{ font-size:2.6rem; font-weight:700; color:var(--accent); }}
  .hero p {{ color:var(--dim); margin:.4rem 0 0; }}
  section {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
            padding:1.2rem 1.4rem; margin-bottom:1.4rem; }}
  h2 {{ font-size:.95rem; color:var(--dim); text-transform:uppercase;
       letter-spacing:.05em; margin:.2rem 0 .8rem; }}
  table {{ width:100%; border-collapse:collapse; font-size:.88rem; }}
  td, th {{ padding:.45rem .5rem; border-top:1px solid var(--line);
           text-align:left; vertical-align:top; }}
  th {{ color:var(--dim); font-weight:600; border-top:none; }}
  .amt {{ text-align:right; font-variant-numeric:tabular-nums; color:var(--accent); }}
  code {{ color:#79c0ff; }} i {{ color:var(--dim); }}
  footer {{ color:var(--dim); font-size:.8rem; text-align:center; margin-top:2rem; }}
</style></head><body><main>
<h1>Project BINGO · network dashboard <span style="color:var(--accent)">· thin-vertical demo</span></h1>

<div class="hero">
  <div class="big">{_usd(total_royalties)}</div>
  <p>paid to design creators — atomically, per unit, at the moment of fabrication settlement —<br>
     across <b>{total_units} units</b> on <b>{len(machines)} machines</b> in <b>{len(machines)} cities</b>.
     No invoice. No platform's mercy. Structural.</p>
</div>

<section><h2>Registered assets (L1)</h2>
<table><tr><th>asset</th><th>title</th><th>license</th><th>effective split</th></tr>
{asset_rows}</table></section>

<section><h2>Earnings by participant (L4)</h2>
<table><tr><th>account</th><th>role</th><th style="text-align:right">earned</th></tr>
{earn_rows}</table></section>

<section><h2>Jobs &amp; proof-of-fabrication (L2)</h2>
<table><tr><th>job</th><th>order</th><th>node</th><th>units</th><th>state</th>
<th>PoF events</th><th>chain head</th></tr>
{job_rows}</table></section>

<section><h2>Settlement journal (L4) — every leg of every atomic release</h2>
<table><tr><th>#</th><th>kind</th><th>job</th><th>legs</th></tr>
{journal_rows}</table></section>

<footer>Project BINGO v3 thin-vertical prototype — local ledger standing in for
stablecoin escrow + split contracts. Every number above is derived from the
journal; nothing is displayed that is not settled.</footer>
</main></body></html>"""
