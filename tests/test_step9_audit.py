"""Acceptance guardrails: a partial session must never count as a full day."""
from datetime import UTC, datetime, timedelta
from scripts.step9_audit import audit


def snapshot():
    opening = datetime(2026, 9, 9, 1, tzinfo=UTC)
    return {'campaign': {'id': 'test', 'planned_start': opening,
                         'planned_end': opening + timedelta(days=7)},
            'runs': [], 'scheduled_cycles': [
                {'market': 'TW', 'scheduled_at': opening + timedelta(minutes=i),
                 'cycle_status': 'completed', 'cycle_id': str(i)} for i in range(271)]}


def test_open_session_and_missing_market_do_not_pass():
    result = audit(snapshot(), datetime(2026, 9, 9, 2, tzinfo=UTC))
    assert result['complete_days'] == {'TW': 0, 'US': 0}
    assert not result['minimum_three_each']


def test_full_session_counts_but_a_missing_cycle_does_not():
    data = snapshot()
    now = datetime(2026, 9, 9, 6, tzinfo=UTC)
    assert audit(data, now)['complete_days']['TW'] == 1
    data['scheduled_cycles'][50].update(cycle_status=None, cycle_id=None)
    result = audit(data, now)
    assert result['complete_days']['TW'] == 0
    assert result['daily_sessions'][0]['missing_due'] == 1


def test_campaign_starting_mid_session_does_not_count():
    data = snapshot()
    data['campaign']['planned_start'] += timedelta(minutes=10)
    assert audit(data, datetime(2026, 9, 9, 6, tzinfo=UTC))['complete_days']['TW'] == 0
