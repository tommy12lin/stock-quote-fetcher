"""Read-only step 9 evidence supplement; run with the deployed application Python."""
import argparse
from collections import defaultdict
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import UUID

from stock_quote_fetcher.config import load_database_config
from stock_quote_fetcher.models import Market
from stock_quote_fetcher.quality import bounds, timezone
from stock_quote_fetcher.storage import Storage


def audit(snapshot, now):
    campaign = snapshot['campaign']
    groups = defaultdict(list)
    for row in snapshot['scheduled_cycles']:
        market = Market(row['market'])
        day = row['scheduled_at'].astimezone(timezone(market)).date()
        groups[(market.value, day)].append(row)
    days = []
    for (market, day), rows in sorted(groups.items()):
        opening, closing = bounds(Market(market), day)
        regular = [r for r in rows if opening <= r['scheduled_at'] <= closing]
        completed = sum(r['cycle_status'] == 'completed' for r in regular)
        due = [r for r in regular if r['scheduled_at'] <= now]
        spans = campaign['planned_start'] <= opening and campaign['planned_end'] > closing
        # Require every scheduled regular-session opportunity, including opening delay.
        full = bool(regular) and spans and now > closing and completed == len(regular)
        days.append(dict(market=market, date=str(day), opening=opening, closing=closing,
                         campaign_spans_session=spans, session_ended=now > closing,
                         planned=len(regular), due=len(due), completed=completed,
                         missing_due=sum(r['cycle_id'] is None for r in due),
                         complete_without_gaps=full))
    first = {}
    seen = set()
    for run in snapshot['runs']:
        for q in run['quotes']:
            if q['id'] in seen:
                continue
            seen.add(q['id'])
            stamp, received = q['quote_time'], q['received_at']
            if stamp is None or received > now or q['price_kind'] != 'last_trade':
                continue
            market = Market(q['market'])
            day = received.astimezone(timezone(market)).date()
            window = bounds(market, day)
            if not window or not (window[0] <= received <= window[1]):
                continue
            if not (window[0] <= stamp <= min(window[1], received)):
                continue
            if q['currency'] != market.currency or q['price'] <= 0:
                continue
            key = (q['market'], q['ticker'], q['provider'])
            if key not in first or received < first[key]['received_at']:
                first[key] = {k: q[k] for k in ('ticker', 'market', 'provider', 'price',
                    'quote_time', 'received_at', 'quality_flags', 'asset_type')}
    counts = {m: sum(d['complete_without_gaps'] for d in days if d['market'] == m)
              for m in ('TW', 'US')}
    return dict(as_of=now, campaign_id=campaign['id'], daily_sessions=days,
                complete_days=counts, minimum_three_each=all(n >= 3 for n in counts.values()),
                first_same_day_intraday=list(first.values()),
                note='Complete days require every planned regular-session cycle completed; '
                     'fetch success and price correctness remain separate acceptance checks.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--campaign-id', type=UUID, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    now = datetime.now(UTC)
    with Storage(load_database_config(args.config)) as storage:
        with storage.report_snapshot():
            result = audit(storage.read_campaign(args.campaign_id, as_of=now), now)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, default=str)
        stream.write('\n')
    print(json.dumps({'complete_days': result['complete_days'],
                      'intraday_samples': len(result['first_same_day_intraday'])}))


if __name__ == '__main__':
    main()
