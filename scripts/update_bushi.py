"""Read the signed-in user's tournament history; never log credentials or raw responses."""
import json
import os
import urllib.request

BASE = 'https://api-user.en.bushi-navi.com'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get(path):
    token = os.environ.get('BUSHI_NAVI_TOKEN', '').strip()
    if not token:
        raise RuntimeError('BUSHI_NAVI_TOKEN is missing')
    request = urllib.request.Request(BASE + path, headers={'X-Authentication': token, 'Accept': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            data = json.load(response)
    except Exception:
        raise RuntimeError('Bushi Navi request failed; check token validity') from None
    if not isinstance(data.get('success'), dict):
        raise RuntimeError('Unexpected Bushi Navi response')
    return data['success']


def schema(value, depth=0):
    if depth > 6:
        return type(value).__name__
    if isinstance(value, dict):
        return {k: schema(v, depth+1) for k,v in value.items()}
    if isinstance(value, list):
        return {'count': len(value), 'item': schema(value[0], depth+1) if value else None}
    return type(value).__name__


if __name__ == '__main__':
    result = get('/api/user/my/event?past_event_display_flg=1&limit=20&offset=0')
    print(json.dumps(schema(result), indent=2))
