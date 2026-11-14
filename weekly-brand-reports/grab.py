"""Save the latest Meta Ads answer to a file without anyone retyping it.

Usage:
  python3 -I grab.py <out.json>                 # take the newest Meta answer from this session's transcript
  python3 -I grab.py <out.json> <saved_path>    # the tool said the full result was saved at <saved_path>

Accepts answers of ads_get_ad_entities ({"ad_entities": ...}) and ads_get_creatives ({"ad_creatives": ...}).
Prints row count and MORE PAGES when the answer has a next cursor (cursor is also written to <out>.cursor).
"""
import json, sys, glob, os, re

out = sys.argv[1]
src = sys.argv[2] if len(sys.argv) > 2 else None
KEYS = ('{"ad_entities"', '{"ad_creatives"')


def from_transcript():
    files = glob.glob('/root/.claude/projects/*/*.jsonl')
    if not files:
        sys.exit('NO TRANSCRIPT FOUND: pass the saved-result path instead')
    tx = max(files, key=os.path.getmtime)
    lines = open(tx).read().splitlines()
    for line in reversed(lines[-120:]):
        if '"tool_result"' not in line:
            continue
        d = json.loads(line)
        if d.get('type') != 'user':
            continue
        for b in d['message']['content']:
            if not isinstance(b, dict) or b.get('type') != 'tool_result':
                continue
            c = b['content']
            t = c if isinstance(c, str) else ''.join(x.get('text', '') for x in c if isinstance(x, dict))
            if t.startswith(KEYS):
                return t
            m = re.search(r'(/\S+?\.txt)', t)
            if m and os.path.exists(m.group(1)):
                body = open(m.group(1)).read()
                if body.lstrip().startswith(KEYS):
                    return body
    sys.exit('NO META ANSWER FOUND in the last tool results')


txt = open(src).read() if src else from_transcript()
o = json.loads(txt)
if o.get('error'):
    sys.exit('META ERROR ' + str(o['error'])[:300])
key = 'ad_entities' if 'ad_entities' in o else 'ad_creatives'
rows = o[key]
rows = json.loads(rows) if isinstance(rows, str) else rows
json.dump({key: rows, 'pagination': o.get('pagination')}, open(out, 'w'), separators=(',', ':'))
nxt = (o.get('pagination') or {}).get('next_cursor')
if nxt:
    open(out + '.cursor', 'w').write(nxt)
print(os.path.basename(out), len(rows), 'rows', 'MORE PAGES' if nxt else '')
