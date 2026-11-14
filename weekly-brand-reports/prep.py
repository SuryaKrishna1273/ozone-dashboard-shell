"""Per-brand helpers for the Monday run.

  python3 -I prep.py dates <brand_key> [YYYY-MM-DD week_end]   -> work dir + every date range the Meta calls need
  python3 -I prep.py subject <brand_key> [--test]               -> Gmail search finding this week's email if already sent
  python3 -I prep.py creative_ids <brand_key>                   -> creative ids with spend in the report week (JSON list)
  python3 -I prep.py thumbs <brand_key>                         -> downloads thumbnails of the top creatives
  python3 -I prep.py config <brand_key>                         -> writes config.json for build_report.py
  python3 -I prep.py email <brand_key> [--test]                 -> subject, recipients, body and attachment reference
"""
import json, sys, os, datetime as dt, hashlib, urllib.request, collections

HERE = os.path.dirname(os.path.abspath(__file__))
BR = json.load(open(os.path.join(HERE, "brands.json")))
cmd, key = sys.argv[1], sys.argv[2]
b = next(x for x in BR["brands"] if x["key"] == key)
WORK = f"/tmp/wbr/{key}"
os.makedirs(WORK + "/raw", exist_ok=True)
STATE = WORK + "/state.json"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def num(x):
    if isinstance(x, dict): x = x.get("value")
    try: return float(x)
    except (TypeError, ValueError): return 0.0


def load(p, k="ad_entities"):
    o = json.load(open(p)); r = o[k]
    return json.loads(r) if isinstance(r, str) else r


if cmd == "dates":
    if len(sys.argv) > 3:
        we = dt.date.fromisoformat(sys.argv[3])
    else:  # last full Monday-Sunday week, in IST
        today = dt.datetime.now(IST).date()
        we = today - dt.timedelta(days=today.weekday() + 1)
    ws = we - dt.timedelta(days=6)
    st = dict(week_end=we.isoformat(), week_start=ws.isoformat(),
              camp_since=(we - dt.timedelta(days=69)).isoformat(),
              ad_since=(ws - dt.timedelta(days=7)).isoformat(),
              acct_since=(ws - dt.timedelta(days=7)).isoformat())
    json.dump(st, open(STATE, "w"))
    print(json.dumps(dict(work=WORK, account=b["account_id"], **st), indent=1))

elif cmd == "subject":
    test = "--test" in sys.argv
    st = json.load(open(STATE))
    we = dt.date.fromisoformat(st["week_end"]); ws = dt.date.fromisoformat(st["week_start"])
    subject = f"{b['brand']} × Epigroww | Meta Ads Weekly Report | {ws.strftime('%-d %b')} – {we.strftime('%-d %b %Y')}"
    if test: subject = "[TEST] " + subject
    print(f'in:sent subject:"{subject}"')

elif cmd == "creative_ids":
    st = json.load(open(STATE))
    s = collections.defaultdict(float)
    for r in load(WORK + "/raw/ad_daily.json"):
        if st["week_start"] <= r["date_start"] <= st["week_end"] and r.get("creative_id"):
            s[r["creative_id"]] += num(r["amount_spent"])
    ids = [k for k, v in sorted(s.items(), key=lambda kv: -kv[1]) if v > 0][:100]
    json.dump(ids, open(WORK + "/creative_ids.json", "w"))
    print(json.dumps(ids))

elif cmd == "thumbs":
    ids = json.load(open(WORK + "/creative_ids.json"))
    cr = {c["id"]: c for c in load(WORK + "/raw/creatives.json", "ad_creatives")}
    os.makedirs(WORK + "/thumbs", exist_ok=True)
    ok = 0
    for i in ids[:15]:
        c = cr.get(i, {}); url = c.get("image_url") or c.get("thumbnail_url")
        if not url: continue
        try:
            open(f"{WORK}/thumbs/{i}.jpg", "wb").write(urllib.request.urlopen(url, timeout=20).read()); ok += 1
        except Exception as e:
            print("thumb failed", i, str(e)[:80])
    print("thumbnails", ok, "of", min(len(ids), 15))

elif cmd == "config":
    st = json.load(open(STATE))
    we = dt.date.fromisoformat(st["week_end"]); ws = dt.date.fromisoformat(st["week_start"])
    out = f"{b['brand'].replace(' ', '_')}_Meta_Weekly_Report_{ws.strftime('%-d')}-{we.strftime('%-d_%b_%Y')}"
    cfg = dict(brand=b["brand"], account_id=b["account_id"], account_name=b["account_name"], week_end=st["week_end"],
               weeks=10, target_roas=b.get("target_roas"), npd_regex=b.get("npd_regex"), top_creatives=10,
               campaign_daily="raw/camp_daily.json", ad_daily="raw/ad_daily.json", creatives="raw/creatives.json",
               account_check_file="raw/acct_weeks.json", out=out)
    json.dump(cfg, open(WORK + "/config.json", "w"), indent=1)
    import shutil; shutil.copy(os.path.join(HERE, "build_report.py"), WORK + "/build_report.py")
    print(WORK + "/config.json")

elif cmd == "email":
    test = "--test" in sys.argv
    st = json.load(open(STATE)); cfg = json.load(open(WORK + "/config.json"))
    we = dt.date.fromisoformat(st["week_end"]); ws = dt.date.fromisoformat(st["week_start"])
    rng = f"{ws.strftime('%-d %b')} – {we.strftime('%-d %b %Y')}"
    pdf = f"{WORK}/{cfg['out']}.pdf"
    if not os.path.exists(pdf): sys.exit("NO PDF: build did not pass")
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    subject = f"{b['brand']} × Epigroww | Meta Ads Weekly Report | {rng}"
    if test: subject = "[TEST] " + subject
    body_html = (f"<p>Hi team,</p><p>Please find attached the Meta Ads weekly report for <b>{b['brand']}</b> "
                 f"covering <b>{rng}</b>, compared with the previous week.</p>"
                 "<p>It covers spend, conversion value, ROAS, cost per purchase, campaign-wise performance and the top creatives of the week.</p>"
                 "<p>Regards,<br>Team Epigroww</p>")
    body_text = (f"Hi team,\n\nPlease find attached the Meta Ads weekly report for {b['brand']} covering {rng}, "
                 "compared with the previous week.\n\nIt covers spend, conversion value, ROAS, cost per purchase, "
                 "campaign-wise performance and the top creatives of the week.\n\nRegards,\nTeam Epigroww")
    print(json.dumps(dict(
        to=[BR["test_recipient"]] if test else b["to"],
        cc=[] if test else b["cc"],
        subject=subject, htmlBody=body_html, body=body_text,
        attachment=dict(filename=os.path.basename(pdf), mimeType="application/pdf", content=f"sha256:{sha}:{pdf}"),
        sent_search=f'in:sent subject:"{subject}"'), indent=1, ensure_ascii=False))
