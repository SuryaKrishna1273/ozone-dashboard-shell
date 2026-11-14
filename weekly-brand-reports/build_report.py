"""Weekly Meta Ads brand report (Mitchell-style layout) -> HTML -> PDF.

Usage: python3 -I build_report.py <config.json>
All numbers come from the saved Meta answers named in the config; nothing is typed by hand.
"""
import json, sys, os, io, base64, re, datetime as dt, collections, html

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

CFG = json.load(open(sys.argv[1]))
BASE = os.path.dirname(os.path.abspath(sys.argv[1]))
P = lambda p: os.path.join(BASE, p)

# ---------------- palette (dataviz reference instance, light) ----------------
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
PREV = "#a9a8a2"
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb"
GOOD, BAD = "#0f7b3f", "#c62828"

for f in font_manager.findSystemFonts():
    if "Inter" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams.update({
    "font.family": "Inter", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "figure.facecolor": "white", "axes.facecolor": "white",
    "legend.frameon": False, "legend.fontsize": 8,
})

# ---------------- load ----------------
def rows(path, key):
    o = json.load(open(P(path)))
    r = o[key]
    return json.loads(r) if isinstance(r, str) else r

def num(x):
    if isinstance(x, dict):
        x = x.get("value")
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0

camp = rows(CFG["campaign_daily"], "ad_entities")
ads = rows(CFG["ad_daily"], "ad_entities")
creatives = {c["id"]: c for c in rows(CFG["creatives"], "ad_creatives")}

D = lambda s: dt.date.fromisoformat(s)
W_END = D(CFG["week_end"]); W_START = W_END - dt.timedelta(days=6)
P_END = W_START - dt.timedelta(days=1); P_START = P_END - dt.timedelta(days=6)
in_w = lambda d: W_START <= D(d) <= W_END
in_p = lambda d: P_START <= D(d) <= P_END
npd = re.compile(CFG["npd_regex"], re.I) if CFG.get("npd_regex") else None

def tot(rs):
    t = dict(spend=0.0, value=0.0, purch=0.0, impr=0.0, clicks=0.0, lpv=0.0)
    for r in rs:
        t["spend"] += num(r["amount_spent"]); t["value"] += num(r["omni_purchase_values"])
        t["purch"] += num(r["omni_purchase"]); t["impr"] += num(r["impressions"])
        t["clicks"] += num(r["link_click"]); t["lpv"] += num(r["omni_landing_page_view"])
    return t

def kpis(t):
    s, v, p = t["spend"], t["value"], t["purch"]
    return dict(spend=s, value=v, roas=v / s if s else None, cpa=s / p if p else None, purch=p,
                aov=v / p if p else None, ctr=t["clicks"] / t["impr"] if t["impr"] else None,
                cplpv=s / t["lpv"] if t["lpv"] else None)

cur = kpis(tot([r for r in camp if in_w(r["date_start"])]))
prv = kpis(tot([r for r in camp if in_p(r["date_start"])]))

# ---------------- gate: everything must tie out before we draw anything ----------------
ad_cur = tot([r for r in ads if in_w(r["date_start"])])
ad_prv = tot([r for r in ads if in_p(r["date_start"])])
problems = []
for name, a, b in (("this week", ad_cur, cur), ("previous week", ad_prv, prv)):
    if abs(a["spend"] - b["spend"]) > 1: problems.append(f"{name}: ad spend {a['spend']:.2f} vs campaign {b['spend']:.2f}")
    if a["purch"] != b["purch"]: problems.append(f"{name}: ad purchases {a['purch']} vs campaign {b['purch']}")
chk = None
if CFG.get("account_check_file"):
    arows = rows(CFG["account_check_file"], "ad_entities")
    byw = {r["date_start"]: r for r in arows}
    def ref(start):
        r = byw.get(start.isoformat())
        if not r: problems.append(f"account total missing for week starting {start}")
        return dict(spend=num(r["amount_spent"]), purch=num(r["omni_purchase"]), value=num(r["omni_purchase_values"])) if r else None
    chk = {"week": ref(W_START), "prev": ref(P_START)}
    if not chk["week"] or not chk["prev"]: chk = None
elif CFG.get("account_check"):
    chk = CFG["account_check"]
else:
    problems.append("no account total to check against")
if chk:
    for name, k, ref in (("this week", cur, chk["week"]), ("previous week", prv, chk["prev"])):
        if abs(k["spend"] - ref["spend"]) > 1 or k["purch"] != ref["purch"] or abs(k["value"] - ref["value"]) > 1:
            problems.append(f"{name}: does not match account total {ref}")
days_seen = {r["date_start"] for r in camp}
for i in range(7):
    if (W_START + dt.timedelta(days=i)).isoformat() not in days_seen: problems.append("missing day in week")
if cur["spend"] <= 0:
    problems.append("no spend in the report week, nothing to report")
if problems:
    sys.exit("GATE FAILED: " + "; ".join(problems))

# ---------------- formatting ----------------
def inr(x, dec=0):
    if x is None: return "–"
    neg = x < 0; x = abs(x)
    s = f"{x:.{dec}f}"; ip, _, fp = s.partition(".")
    if len(ip) > 3:
        head, tail = ip[:-3], ip[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        ip = head + "," + tail
    return ("-" if neg else "") + "₹" + ip + ("." + fp if fp else "")

def intf(x):
    return inr(x).replace("₹", "") if x is not None else "–"

def pct(a, b):
    if a is None or b in (None, 0): return None
    return (a - b) / b * 100

def ax_inr(v, _):
    if v >= 1e5: return f"₹{v/1e5:.1f}L"
    if v >= 1e3: return f"₹{v/1e3:.0f}K"
    return f"₹{v:.0f}"

def svg(fig):
    buf = io.StringIO(); fig.savefig(buf, format="svg", bbox_inches="tight"); plt.close(fig)
    s = buf.getvalue()
    return s[s.index("<svg"):]

dlabel = lambda d: d.strftime("%-d %b")

# ---------------- weekly series (10 weeks ending W_END) ----------------
NWEEKS = CFG.get("weeks", 10)
weeks = []
for i in range(NWEEKS - 1, -1, -1):
    e = W_END - dt.timedelta(days=7 * i); s = e - dt.timedelta(days=6)
    t = kpis(tot([r for r in camp if s <= D(r["date_start"]) <= e]))
    weeks.append((s, e, t))
if D(min(days_seen)) > weeks[0][0]:
    sys.exit("GATE FAILED: campaign file does not cover the 10-week trend")

def week_bars(metric, color, title, fmt, target=None):
    fig, ax = plt.subplots(figsize=(5.2, 2.5))
    xs = range(len(weeks)); vals = [w[2][metric] or 0 for w in weeks]
    bars = ax.bar(xs, vals, color=color, width=0.62, zorder=2)
    bars[-1].set_edgecolor(INK); bars[-1].set_linewidth(1.2)
    ax.set_xticks(list(xs)); ax.set_xticklabels([dlabel(w[0]) for w in weeks], fontsize=7.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(fmt))
    if target:
        ax.axhline(target, color=INK2, ls=(0, (4, 3)), lw=1.2, zorder=3)
        ax.text(len(weeks) - 0.5, target, f" Target {target:g}x", va="bottom", ha="right", fontsize=7.5, color=INK2)
    ax.text(len(weeks) - 1, vals[-1], fmt(vals[-1], None), ha="center", va="bottom", fontsize=7.5, color=INK, fontweight="semibold")
    ax.set_ylim(0, max(vals + [target or 0]) * 1.18)
    return svg(fig)

roas_week_svg = week_bars("roas", SERIES[0], "ROAS", lambda v, _: f"{v:.2f}x", CFG.get("target_roas"))
spend_week_svg = week_bars("spend", SERIES[1], "Spend", ax_inr)

# ---------------- daily: this week vs previous 7 days ----------------
def daily(rs, start):
    out = []
    for i in range(7):
        d = (start + dt.timedelta(days=i)).isoformat()
        out.append(kpis(tot([r for r in rs if r["date_start"] == d])))
    return out

cur_daily, prv_daily = daily(camp, W_START), daily(camp, P_START)
day_labels = [dlabel(W_START + dt.timedelta(days=i)) for i in range(7)]

def vs_prev(metric, fmt):
    fig, ax = plt.subplots(figsize=(5.2, 2.5))
    c = [d[metric] for d in cur_daily]; p = [d[metric] for d in prv_daily]
    ax.plot(range(7), p, color=PREV, lw=2, ls=(0, (4, 2)), marker="o", ms=4, label="Previous 7 days", zorder=2)
    ax.plot(range(7), c, color=SERIES[0], lw=2, marker="o", ms=5, label="This week", zorder=3,
            markeredgecolor="white", markeredgewidth=1)
    for i, v in enumerate(c):
        if v is not None:
            ax.annotate(fmt(v, None), (i, v), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=7, color=INK)
    ax.set_xticks(range(7)); ax.set_xticklabels(day_labels, fontsize=7.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(fmt))
    allv = [v for v in c + p if v is not None]
    ax.set_ylim(0, max(allv) * 1.25 if allv else 1)
    ax.legend(loc="upper left", ncol=2, bbox_to_anchor=(0, 1.16))
    return svg(fig)

cpa_vs_svg = vs_prev("cpa", lambda v, _: inr(v))
roas_vs_svg = vs_prev("roas", lambda v, _: f"{v:.2f}x")

# ---------------- campaigns ----------------
by_c = collections.defaultdict(list)
for r in camp: by_c[r["id"]].append(r)
cnames = {r["id"]: r["name"] for r in camp}
cstatus = {r["id"]: r.get("effective_status", "") for r in camp}
ctab = []
for cid, rs in by_c.items():
    w = kpis(tot([r for r in rs if in_w(r["date_start"])])); pv = kpis(tot([r for r in rs if in_p(r["date_start"])]))
    if w["spend"] > 0 or pv["spend"] > 0:
        ctab.append(dict(id=cid, name=" ".join(cnames[cid].split()), w=w, p=pv, status=cstatus[cid],
                         seg=("NPD" if npd and npd.search(cnames[cid]) else "BAU")))
ctab.sort(key=lambda x: -x["w"]["spend"])
TOPN = 5
top = [c for c in ctab if c["w"]["spend"] > 0][:TOPN]
color_of = {c["id"]: SERIES[i] for i, c in enumerate(top)}
short = lambda n, k=34: n if len(n) <= k else n[:k - 1] + "…"

def by_campaign(metric, fmt):
    fig, ax = plt.subplots(figsize=(5.2, 2.5))
    for c in top:
        vals = []
        for i in range(7):
            d = (W_START + dt.timedelta(days=i)).isoformat()
            vals.append(kpis(tot([r for r in by_c[c["id"]] if r["date_start"] == d]))[metric])
        ax.plot(range(7), vals, color=color_of[c["id"]], lw=2, marker="o", ms=4, label=short(c["name"], 30),
                markeredgecolor="white", markeredgewidth=0.8)
    ax.set_xticks(range(7)); ax.set_xticklabels(day_labels, fontsize=7.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(fmt))
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, fontsize=7.5, columnspacing=1.2)
    return svg(fig)

cpa_camp_svg = by_campaign("cpa", lambda v, _: inr(v))
roas_camp_svg = by_campaign("roas", lambda v, _: f"{v:.1f}x")

# scatter: campaign spend vs CPA (this week)
sc = [c for c in ctab if c["w"]["spend"] > 0 and c["w"]["cpa"]]
fig, ax = plt.subplots(figsize=(10.8, 3.0))
if not sc:
    sc = []
avg_spend = (sum(c["w"]["spend"] for c in sc) / len(sc)) if sc else 0
placed = []
xr = max([c["w"]["spend"] for c in sc] or [1]); yr = max([c["w"]["cpa"] for c in sc] or [1])
for c in sorted(sc, key=lambda c: c["w"]["cpa"]):
    col = color_of.get(c["id"], "#6b6a65")
    x, y = c["w"]["spend"], c["w"]["cpa"]
    ax.scatter(x, y, s=90, color=col, edgecolor="white", linewidth=1.5, zorder=3)
    near = sum(1 for (px, py) in placed if abs(px - x) < xr * 0.08 and abs(py - y) < yr * 0.08)
    ha = "right" if x > xr * 0.8 else "left"
    ax.annotate(short(c["name"], 30), (x, y), textcoords="offset points",
                xytext=((-8 if ha == "right" else 8), 4 - 11 * near), ha=ha, fontsize=7, color=INK2)
    placed.append((x, y))
if cur["cpa"]: ax.axhline(cur["cpa"], color=INK2, ls=(0, (4, 3)), lw=1)
ax.set_xlim(left=0)
if cur["cpa"]: ax.text(ax.get_xlim()[1] * 0.5, cur["cpa"], f"Account CPA {inr(cur['cpa'])}", ha="center", va="bottom", fontsize=7.5, color=INK2,
        bbox=dict(facecolor="white", edgecolor="none", pad=1))
ax.axvline(avg_spend, color=INK2, ls=(0, (4, 3)), lw=1)
ax.text(avg_spend, ax.get_ylim()[1], f" Avg spend {inr(avg_spend)}", ha="left", va="top", fontsize=7.5, color=INK2)
ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(ax_inr))
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: inr(v)))
ax.set_xlabel("Amount spent (this week)"); ax.set_ylabel("Cost per purchase")
ax.set_xlim(left=0); ax.set_ylim(bottom=0)
scatter_svg = svg(fig)

# ---------------- creatives (ads) ----------------
by_a = collections.defaultdict(list)
for r in ads: by_a[r["id"]].append(r)
atab = []
for aid, rs in by_a.items():
    w = kpis(tot([r for r in rs if in_w(r["date_start"])]))
    if w["spend"] <= 0: continue
    m = rs[0]
    created = dt.datetime.strptime(m["created_time"][:19], "%Y-%m-%dT%H:%M:%S")
    atab.append(dict(id=aid, name=" ".join(m["name"].split()), camp=" ".join(m["campaign_name"].split()),
                     created=created, creative=m.get("creative_id"), w=w))
atab.sort(key=lambda x: -x["w"]["spend"])

def thumb(cid):
    p = P(f"thumbs/{cid}.jpg")
    if cid and os.path.exists(p) and os.path.getsize(p) > 300:
        return "data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()
    return None

NCRE = CFG.get("top_creatives", 10)

# ---------------- HTML ----------------
def delta(a, b, good_up=True, neutral=False):
    d = pct(a, b)
    if d is None: return '<span class="d muted">–</span>'
    up = d >= 0
    cls = "muted" if neutral else ("good" if up == good_up else "bad")
    return f'<span class="d {cls}">{"▲" if up else "▼"} {abs(d):.1f}%</span>'

tiles = [
    ("Amount Spent", inr(cur["spend"]), delta(cur["spend"], prv["spend"], neutral=True)),
    ("Purchase Conversion Value", inr(cur["value"]), delta(cur["value"], prv["value"])),
    ("Purchase ROAS", f"{cur['roas']:.2f}x" if cur["roas"] else "–", delta(cur["roas"], prv["roas"])),
    ("Cost per Purchase", inr(cur["cpa"]), delta(cur["cpa"], prv["cpa"], good_up=False)),
    ("Purchases", intf(cur["purch"]), delta(cur["purch"], prv["purch"])),
    ("AOV", inr(cur["aov"]), delta(cur["aov"], prv["aov"])),
]

def rx(v): return f"{v:.2f}x" if v else "–"

def ctr_s(x): return f"{x*100:.2f}%" if x is not None else "–"

camp_rows = "".join(
    f"<tr><td class='l'>{html.escape(c['name'])}{' <span class=tag>NPD</span>' if npd and c['seg']=='NPD' else ''}</td>"
    f"<td>{inr(c['w']['spend'])}</td><td>{inr(c['w']['value'])}</td>"
    f"<td>{rx(c['w']['roas'])}</td>"
    f"<td>{intf(c['w']['purch'])}</td><td>{inr(c['w']['cpa'])}</td>"
    f"<td>{delta(c['w']['spend'], c['p']['spend'], neutral=True)}</td>"
    f"<td>{delta(c['w']['roas'], c['p']['roas'])}</td></tr>"
    for c in ctab if c["w"]["spend"] > 0)
camp_total = (f"<tr class='tot'><td class='l'>Total</td><td>{inr(cur['spend'])}</td><td>{inr(cur['value'])}</td>"
              f"<td>{rx(cur['roas'])}</td><td>{intf(cur['purch'])}</td><td>{inr(cur['cpa'])}</td>"
              f"<td>{delta(cur['spend'], prv['spend'], neutral=True)}</td><td>{delta(cur['roas'], prv['roas'])}</td></tr>")

seg_html = ""
if npd:
    segs = []
    for s in ("BAU", "NPD"):
        w = kpis(tot([r for r in camp if in_w(r["date_start"]) and (("NPD" if npd.search(r["name"]) else "BAU") == s)]))
        pv = kpis(tot([r for r in camp if in_p(r["date_start"]) and (("NPD" if npd.search(r["name"]) else "BAU") == s)]))
        segs.append(f"<tr><td class='l'><b>{s}</b></td><td>{inr(w['spend'])}</td><td>{inr(w['value'])}</td>"
                    f"<td>{rx(w['roas'])}</td><td>{intf(w['purch'])}</td><td>{inr(w['cpa'])}</td>"
                    f"<td>{delta(w['spend'], pv['spend'], neutral=True)}</td><td>{delta(w['roas'], pv['roas'])}</td></tr>")
    seg_html = f"""<section class="card"><h2>BAU vs NPD</h2>
    <table><thead><tr><th class='l'>Segment</th><th>Spend</th><th>Conv. value</th><th>ROAS</th><th>Purchases</th><th>CPA</th><th>Spend WoW</th><th>ROAS WoW</th></tr></thead>
    <tbody>{''.join(segs)}</tbody></table></section>"""

cre_rows = []
for i, a in enumerate(atab[:NCRE]):
    t = thumb(a["creative"])
    img = f"<img src='{t}'>" if t else "<div class='noimg'>–</div>"
    w = a["w"]
    cre_rows.append(
        f"<tr><td class='n'>{i+1}.</td><td class='th'>{img}</td><td class='l nm'>{html.escape(a['name'])}</td>"
        f"<td class='l cp'>{html.escape(a['camp'])}</td><td class='l dt'>{a['created'].strftime('%-d %b %Y')}</td>"
        f"<td>{inr(w['spend'])}</td><td>{rx(w['roas'])}</td>"
        f"<td>{intf(w['purch'])}</td><td>{inr(w['cpa'])}</td><td>{inr(w['cplpv'], 2)}</td><td>{ctr_s(w['ctr'])}</td></tr>")
shown = atab[:NCRE]
cre_total = (f"<tr class='tot'><td></td><td></td><td class='l'>Top {len(shown)} of {len(atab)} ads</td><td></td><td></td>"
             f"<td>{inr(sum(a['w']['spend'] for a in shown))}</td><td></td><td>{intf(sum(a['w']['purch'] for a in shown))}</td>"
             f"<td></td><td></td><td></td></tr>")

wk = f"{W_START.strftime('%-d %b')} – {W_END.strftime('%-d %b %Y')}"
pk = f"{P_START.strftime('%-d %b')} – {P_END.strftime('%-d %b')}"
made = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).strftime("%-d %b %Y, %-I:%M %p IST")

HTML = f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(CFG['brand'])} — Meta Ads Weekly Report</title>
<style>
@page {{ size: 1100px 3000px; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: Inter, sans-serif; color: {INK}; background: #f3f2ee; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.wrap {{ width: 1100px; padding: 0 0 28px; }}
header {{ background: #ffffff; padding: 22px 32px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid {GRID}; }}
header h1 {{ font-size: 22px; font-weight: 600; margin: 0; letter-spacing: -0.01em; }}
header .sub {{ font-size: 12px; color: {INK2}; margin-top: 4px; }}
.range {{ text-align: right; }}
.range .r1 {{ font-size: 15px; font-weight: 600; padding: 8px 14px; border: 1px solid {GRID}; border-radius: 6px; background: {SURF}; display: inline-block; }}
.range .r2 {{ font-size: 11px; color: {MUTED}; margin-top: 6px; }}
.grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px 32px 0; }}
.full {{ padding: 16px 32px 0; }}
.card {{ background: #fff; border: 1px solid {GRID}; border-radius: 10px; padding: 14px 16px 10px; }}
.card h2 {{ font-size: 13px; font-weight: 600; margin: 0 0 6px; }}
.card .hint {{ font-size: 10.5px; color: {MUTED}; margin: -2px 0 6px; }}
.card svg {{ width: 100%; height: auto; display: block; }}
.kpis {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; padding: 16px 32px 0; }}
.kpi {{ background: #fff; border: 1px solid {GRID}; border-radius: 10px; padding: 14px 14px 12px; }}
.kpi .k {{ font-size: 11px; color: {INK2}; }}
.kpi .v {{ font-size: 24px; font-weight: 600; margin: 6px 0 4px; letter-spacing: -0.01em; }}
.kpi .p {{ font-size: 10.5px; color: {MUTED}; margin-left: 6px; }}
.d {{ font-size: 11.5px; font-weight: 600; white-space: nowrap; }}
.good {{ color: {GOOD}; }} .bad {{ color: {BAD}; }} .muted {{ color: {MUTED}; }}
table {{ width: 100%; border-collapse: collapse; font-size: 11.5px; }}
th {{ font-weight: 600; color: {INK2}; text-align: right; padding: 8px 8px; border-bottom: 1px solid {GRID}; background: {SURF}; font-size: 11px; }}
td {{ text-align: right; padding: 8px 8px; border-bottom: 1px solid #efeee9; font-variant-numeric: tabular-nums; vertical-align: middle; }}
.l {{ text-align: left; }}
tr.tot td {{ font-weight: 600; border-top: 1px solid {INK2}; border-bottom: none; }}
.tag {{ font-size: 9.5px; font-weight: 600; color: {INK2}; border: 1px solid {GRID}; border-radius: 4px; padding: 1px 5px; margin-left: 4px; }}
td.th img {{ width: 52px; height: 52px; object-fit: cover; border-radius: 6px; display: block; border: 1px solid {GRID}; }}
.noimg {{ width: 52px; height: 52px; border-radius: 6px; background: #efeee9; color: {MUTED}; display: flex; align-items: center; justify-content: center; }}
td.nm {{ max-width: 230px; font-weight: 500; }} td.cp {{ max-width: 200px; color: {INK2}; font-size: 10.5px; }} td.dt {{ color: {INK2}; white-space: nowrap; font-size: 10.5px; }}
td.n {{ color: {MUTED}; width: 24px; }}
footer {{ padding: 14px 32px 0; font-size: 10px; color: {MUTED}; line-height: 1.5; }}
</style></head><body><div class="wrap">
<header><div><h1>{html.escape(CFG['brand'])} — Meta Ads Weekly Report</h1><div class="sub">Prepared by Epigroww · Ad account {html.escape(CFG['account_name'])}</div></div>
<div class="range"><div class="r1">{wk}</div><div class="r2">Compared with previous 7 days ({pk})</div></div></header>

<div class="grid2">
<section class="card"><h2>Purchase ROAS by week</h2><div class="hint">Last {NWEEKS} weeks · outlined bar = this week</div>{roas_week_svg}</section>
<section class="card"><h2>Amount spent by week</h2><div class="hint">Last {NWEEKS} weeks · outlined bar = this week</div>{spend_week_svg}</section>
</div>

<div class="kpis">{''.join(f'<div class="kpi"><div class="k">{k}</div><div class="v">{v}</div>{d}<span class="p">vs prev. week</span></div>' for k, v, d in tiles)}</div>

<div class="grid2">
<section class="card"><h2>Cost per purchase over time</h2>{cpa_vs_svg}</section>
<section class="card"><h2>Cost per purchase by campaign</h2><div class="hint">Top {len(top)} campaigns by spend this week</div>{cpa_camp_svg}</section>
<section class="card"><h2>Purchase ROAS over time</h2>{roas_vs_svg}</section>
<section class="card"><h2>Purchase ROAS by campaign</h2><div class="hint">Top {len(top)} campaigns by spend this week</div>{roas_camp_svg}</section>
</div>

<div class="full"><section class="card"><h2>Spend vs cost per purchase, by campaign</h2><div class="hint">Bottom-right = spending a lot at a low CPA (good). Top-right = spending a lot at a high CPA (watch).</div>{scatter_svg}</section></div>

{('<div class="full">' + seg_html + '</div>') if seg_html else ''}

<div class="full"><section class="card"><h2>Campaigns this week</h2>
<table><thead><tr><th class='l'>Campaign</th><th>Spend</th><th>Conv. value</th><th>ROAS</th><th>Purchases</th><th>CPA</th><th>Spend WoW</th><th>ROAS WoW</th></tr></thead>
<tbody>{camp_rows}{camp_total}</tbody></table></section></div>

<div class="full"><section class="card"><h2>Top creatives this week</h2>
<table><thead><tr><th></th><th></th><th class='l'>Ad creative</th><th class='l'>Campaign</th><th class='l'>Created</th><th>Spend</th><th>ROAS</th><th>Purchases</th><th>CPA</th><th>Cost / LPV</th><th>Link CTR</th></tr></thead>
<tbody>{''.join(cre_rows)}{cre_total}</tbody></table></section></div>

<footer>Source: Meta Ads, account {html.escape(CFG['account_id'])}. Purchases and conversion value use Meta's "Purchases" (all channels) with the account's attribution setting, so they match Ads Manager.
ROAS = conversion value ÷ spend · CPA = spend ÷ purchases · AOV = conversion value ÷ purchases · Link CTR = link clicks ÷ impressions.
Every total in this report was checked against the account total before it was made. Generated {made}.</footer>
</div></body></html>"""

out_html = P(CFG["out"] + ".html")
open(out_html, "w").write(HTML)

# ---------------- PDF ----------------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    exe = None
    for root, _, files in os.walk("/opt/pw-browsers"):
        if "chrome" in files and "chrome-linux" in root:
            exe = os.path.join(root, "chrome"); break
    b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1100, "height": 1000})
    pg.goto("file://" + out_html); pg.wait_for_timeout(300)
    h = pg.evaluate("document.querySelector('.wrap').getBoundingClientRect().height")
    pg.add_style_tag(content=f"@page {{ size: 1100px {int(h)+2}px; margin: 0; }}")
    pg.pdf(path=P(CFG["out"] + ".pdf"), width="1100px", height=f"{int(h)+2}px", print_background=True)
    pg.screenshot(path=P(CFG["out"] + "_preview.png"), full_page=True)
    b.close()

summary = dict(week=wk, spend=round(cur["spend"], 2), value=round(cur["value"], 2), roas=round(cur["roas"], 4),
               purch=cur["purch"], cpa=round(cur["cpa"], 2), prev_spend=round(prv["spend"], 2), prev_purch=prv["purch"],
               campaigns=len([c for c in ctab if c["w"]["spend"] > 0]), ads=len(atab))
print(json.dumps(summary))
print("GATE OK")
