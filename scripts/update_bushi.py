"""Read the signed-in user's tournament history; never log credentials or raw responses."""
import json
import os
import urllib.request
import urllib.error

BASE = 'https://api-user.en.bushi-navi.com'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get(path, optional=False):
    token = os.environ.get('BUSHI_NAVI_TOKEN', '').strip()
    if not token:
        raise RuntimeError('BUSHI_NAVI_TOKEN is missing')
    request = urllib.request.Request(BASE + path, headers={'X-Authentication': token, 'Accept': 'application/json', 'X-Accept-Version': 'v1', 'Accept-Language': 'en'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        if optional and error.code in (400, 404):
            return None
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
            events[event['id']] = dict(event, title=series['title'], game_title_id=series['game_title_id'], logo=series.get('logo_file', ''))
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


def standing_summary(standing, rank):
    """Reduce standings to own result + aggregate size; discard opponents' data."""
    entrants = {}
    for key in ('swiss_rankings', 'braket_single_rankings'):
        values = standing.get(key)
        if not isinstance(values, list):
            raise RuntimeError('Unexpected standings format')
        for row in values:
            if row.get('status_id') in (4, 5, 8):
                continue
            identity = row.get('id')
            if not isinstance(identity, int):
                raise RuntimeError('Missing standings entry ID')
            entrants[identity] = row
    size = len(entrants)
    # Group ranks cannot safely be compared to a whole-event denominator.
    comparable = (not standing.get('use_group') and size > 1
                  and isinstance(rank, int) and 0 < rank <= size
                  and any(r.get('is_own_team') for r in entrants.values()))
    return {'rank': rank if isinstance(rank, int) and rank > 0 else None,
            'size': size if not standing.get('use_group') and size else None,
            'unit': 'teams' if standing.get('team_count', 1) > 1 else 'players',
            'comparable': comparable}


def best_event(events, results):
    from fractions import Fraction
    candidates = [e for e in events if results[e['id']]['comparable']]
    return min(candidates, key=lambda e: (Fraction(results[e['id']]['rank'], results[e['id']]['size']),
                                         -results[e['id']]['size'], -e['id'])) if candidates else None


def registered_decks(data):
    if data is None:
        return []
    decks = data.get('decks')
    if not isinstance(decks, list):
        raise RuntimeError('Unexpected registered deck response')
    result = []
    for deck in sorted(decks, key=lambda d: d.get('deck_number', 0)):
        code = deck.get('deck_recipe_id')
        if code is None or code == '':
            continue
        if not isinstance(code, str):
            raise RuntimeError('Unexpected deck code format')
        result.append(code.strip())
    return list(dict.fromkeys(code for code in result if code))


def render(events, games, results):
    from html import escape
    from datetime import datetime, timezone
    from urllib.parse import urlparse
    def artwork(event, width):
        url = event.get('logo') or games[str(event['game_title_id'])].get('file_url', '')
        host = urlparse(url).hostname or ''
        if not url.startswith('https://') or not (host.endswith('.amazonaws.com') or host.endswith('.bushi-navi.com')):
            return ''
        return f'<img src="{escape(url, quote=True)}" width="{width}" alt="{escape(event["title"], quote=True)}">'
    def deck_text(event):
        codes = results[event['id']].get('decks', [])
        if not codes:
            return ''
        label = 'Deck' if len(codes) == 1 else 'Decks'
        return '<br><sub>' + label + ': ' + ' · '.join('<code>' + escape(code) + '</code>' for code in codes) + '</sub>'
    def rank_text(result):
        rank = f'#{result["rank"]}' if result['rank'] else 'Not recorded'
        if result['size']:
            rank += f' / {result["size"]} {result["unit"]}'
        return rank
    best = best_event(events, results)
    comparable = sum(r['comparable'] for r in results.values())
    wins = sum(r['rank'] == 1 for r in results.values())
    metrics = ('<table width="700"><tr>'
               f'<td align="center" width="33%"><sub>ATTENDED</sub><br><h2>{len(events)}</h2></td>'
               f'<td align="center" width="33%"><sub>FIRST PLACE</sub><br><h2>{wins}</h2></td>'
               f'<td align="center" width="33%"><sub>RANKED WITH FIELD SIZE</sub><br><h2>{comparable}</h2></td>'
               '</tr></table>')
    featured = ''
    if best:
        result = results[best['id']]
        percent = 100 * result['rank'] / result['size']
        featured = ('<h4>Best Relative Finish</h4>\n<table width="700"><tr>'
                    f'<td align="center" width="190">{artwork(best, 170)}</td>'
                    '<td align="left">'
                    f'<strong>{escape(best["title"])}</strong><br><br>'
                    f'<strong>{rank_text(result)} · Top {percent:.1f}%</strong><br>'
                    f'<sub>{escape(best["start_local_date"])} · {escape(games[str(best["game_title_id"])]["title_short"])}</sub>{deck_text(best)}'
                    '</td></tr></table>')
    rows = []
    for event in events[:5]:
        game = games[str(event['game_title_id'])]['title_short']
        rows.append('<tr>'
                    f'<td align="center" width="130">{artwork(event, 110)}</td>'
                    f'<td><strong>{escape(event["title"])}</strong><br>'
                    f'<sub>{escape(event["start_local_date"])} · {escape(game)}</sub>{deck_text(event)}</td>'
                    f'<td align="center"><strong>{rank_text(results[event["id"]])}</strong></td></tr>')
    recent = '<h4>Recent Tournaments</h4>\n<table width="700">\n' + '\n'.join(rows) + '\n</table>' if rows else '<p>No completed tournament entries.</p>'
    date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    return ('<!-- bushi:start -->\n<div align="center">\n\n<h3>Tournament Record</h3>\n'
            '<p><sub><a href="https://www.en.bushi-navi.com/">Bushi Navi ↗</a></sub></p>\n\n'
            + metrics + '\n\n' + featured + '\n\n' + recent
            + '\n\n<details><summary>How results are counted</summary>\n\n'
            '<p><sub>Completed, attended event entries only; canceled, waitlisted and absent entries excluded.<br>'
            'Field size comes from unique standings entries, not venue capacity; team events count teams.<br>'
            'Best relative finish = lowest rank / field size; ties favor the larger field.<br>'
            'Missing or grouped standings are excluded from this comparison. This is a profile metric, not an official rating.<br>'
            f'Updated {date} UTC</sub></p>\n\n</details>\n\n</div>\n<!-- bushi:end -->')


def main():
    from pathlib import Path
    events = fetch_events()
    master = get('/api/masterdata')
    games = master.get('game_title', master.get('master', {}).get('game_title'))
    if not isinstance(games, dict):
        raise RuntimeError('Game title data unavailable')
    from concurrent.futures import ThreadPoolExecutor
    import time
    def fetch_result(event):
        history = get(f"/api/user/event/{event['id']}/history", optional=True)
        time.sleep(0.15)
        standing = get(f"/api/user/event/{event['id']}/standing", optional=True)
        time.sleep(0.15)
        user = history.get('user') if history else None
        rank = user.get('rank') if isinstance(user, dict) else None
        if standing is None:
            return event['id'], {'rank': rank if isinstance(rank, int) and rank > 0 else None,
                                 'size': None, 'unit': 'players', 'comparable': False}
        return event['id'], standing_summary(standing, rank)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = dict(pool.map(fetch_result, events))
    displayed = {event['id'] for event in events[:5]}
    best = best_event(events, results)
    if best:
        displayed.add(best['id'])
    for event_id in displayed:
        results[event_id]['decks'] = registered_decks(get(f'/api/user/{event_id}/deckrecipe_id', optional=True))
    section = render(events, games, results)
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
