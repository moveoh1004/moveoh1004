"""Read the signed-in user's tournament history; never log credentials or raw responses."""
import json
import os
import urllib.request
import urllib.error

BASE = 'https://api-user.en.bushi-navi.com'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get(path):
    token = os.environ.get('BUSHI_NAVI_TOKEN', '').strip()
    if not token:
        raise RuntimeError('BUSHI_NAVI_TOKEN is missing')
    request = urllib.request.Request(BASE + path, headers={'X-Authentication': token, 'Accept': 'application/json', 'X-Accept-Version': 'v1', 'Accept-Language': 'en'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'Bushi Navi returned HTTP {error.code}') from None
    except urllib.error.URLError:
        raise RuntimeError('Bushi Navi connection failed') from None
    except Exception:
        raise RuntimeError('Bushi Navi request failed; check token validity') from None
    if not isinstance(data.get('success'), dict):
        raise RuntimeError('Unexpected Bushi Navi response')
    return data['success']



def completed_events(series_list):
    events = {}
    for series in series_list:
        for event in series['events']:
            # Only checked-in/playing/dropped entries in finished events.
            if event['status_id'] != 61 or event['team_status_id'] not in (6, 10, 11) or event['is_canceled']:
                continue
            events[event['id']] = dict(event, title=series['title'], game_title_id=series['game_title_id'])
    return sorted(events.values(), key=lambda e: (e['start_local_date'], e['id']), reverse=True)


def fetch_events():
    series = []
    for page in range(50):
        result = get(f'/api/user/my/event?past_event_display_flg=1&limit=100&offset={page*100}')
        batch = result['event_series']
        if not isinstance(batch, list) or not isinstance(result['total'], int):
            raise RuntimeError('Unexpected event list')
        series.extend(batch)
        if len(series) >= result['total']:
            return completed_events(series)
        if not batch:
            raise RuntimeError('Incomplete event list; previous history preserved')
    raise RuntimeError('Pagination limit reached; previous history preserved')


def render(events, games, histories):
    from html import escape
    from datetime import datetime, timezone
    rows = []
    for event in events[:5]:
        game = games[str(event['game_title_id'])]['title_short']
        rank = histories[event['id']]['user'].get('rank')
        result = f'#{rank}' if isinstance(rank, int) and rank > 0 else 'Not recorded'
        rows.append('<tr>' + ''.join(f'<td>{escape(str(value))}</td>' for value in
                    [event['start_local_date'], game, event['title'], result]) + '</tr>')
    table = ('<table>\n<tr><th>Date</th><th>Game</th><th>Tournament</th><th>Rank</th></tr>\n'
             + '\n'.join(rows) + '\n</table>') if rows else '<p><sub>No completed tournament entries.</sub></p>'
    date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    return ('<!-- bushi:start -->\n<div align="center">\n\n<h3>Tournament History</h3>\n'
            '<p><sub>Latest 5 attended events · <a href="https://www.en.bushi-navi.com/">Bushi Navi ↗</a></sub></p>\n\n'
            + table + f'\n\n<p><sub>Recorded event rank · Updated {date} UTC</sub></p>\n\n</div>\n<!-- bushi:end -->')


def main():
    from pathlib import Path
    events = fetch_events()
    master = get('/api/masterdata')
    games = master.get('game_title', master.get('master', {}).get('game_title'))
    if not isinstance(games, dict):
        raise RuntimeError('Game title data unavailable')
    histories = {e['id']: get(f"/api/user/event/{e['id']}/history") for e in events[:5]}
    section = render(events, games, histories)
    path = Path(__file__).resolve().parents[1] / 'README.md'
    current = path.read_text()
    start, end = '<!-- bushi:start -->', '<!-- bushi:end -->'
    if start not in current and end not in current:
        updated = current.rstrip() + '\n\n' + section + '\n'
    elif current.count(start) == current.count(end) == 1 and current.index(start) < current.index(end):
        before, rest = current.split(start)
        _, after = rest.split(end)
        updated = before + section + after
    else:
        raise RuntimeError('Invalid tournament section markers')
    if updated != current:
        path.write_text(updated)
    print(f'Tournament history updated: {min(len(events), 5)} entries')


if __name__ == '__main__':
    main()
