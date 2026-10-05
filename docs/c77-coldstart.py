"""C7-7-1: pair every instance start with that instance's first requests. Reads the local log export only."""
import json, sys
from datetime import datetime

def ts(s):
    s = s.rstrip('Z')
    if '.' in s:
        head, frac = s.split('.')
        s = f'{head}.{frac[:6]}'
    return datetime.fromisoformat(s)

d = json.load(open(sys.argv[1], encoding='utf-8-sig'))
d.sort(key=lambda e: e['timestamp'])
starts = [e for e in d if 'Starting new instance' in (e.get('textPayload') or '')]
for s in starts:
    inst = s['labels']['instanceId']
    # A request that triggers the start is stamped on arrival, before the start event.
    same = [e for e in d if e.get('labels', {}).get('instanceId') == inst]
    listen = next((e for e in same if 'listening' in str(e.get('textPayload') or e.get('jsonPayload') or '')), None)
    reqs = [e for e in same if 'httpRequest' in e][:2]
    t0 = ts(s['timestamp'])
    line = [s['timestamp'][:19], s['labels'].get('scaling_reason', '?'), s['resource']['labels'].get('revision_name', '?')[-9:]]
    line.append(f"listen+{(ts(listen['timestamp']) - t0).total_seconds():.2f}" if listen else 'listen=?')
    for r in reqs:
        h = r['httpRequest']
        url = h['requestUrl'].split('.run.app')[-1].split('?')[0]
        line.append(f"[{r['timestamp'][11:23]} +{(ts(r['timestamp']) - t0).total_seconds():.2f}s {h['requestMethod']} {url} {h.get('status')} {float(h['latency'].rstrip('s')):.3f}s]")
    print(' '.join(line))
