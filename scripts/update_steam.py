"""Update only the Steam section from the user's public Steam profile XML."""

import argparse
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import re
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

PROFILE = "https://steamcommunity.com/id/moveOH/"
STEAM_ID = "76561198296075276"
START = "<!-- steam:start -->"
END = "<!-- steam:end -->"
README = Path(__file__).resolve().parents[1] / "README.md"


def render(data):
    root = ET.fromstring(data)
    if root.tag != "profile" or root.findtext("steamID64") != STEAM_ID:
        raise ValueError("Unexpected Steam profile response; keeping previous section")
    if root.findtext("privacyState") != "public":
        raise ValueError("Steam profile is not public; keeping previous section")
    games = root.find("mostPlayedGames")
    if games is None:
        raise ValueError("Steam game list unavailable; keeping previous section")
    cards = []
    for game in games.findall("mostPlayedGame")[:4]:
        name = (game.findtext("gameName") or "").strip()
        link = game.findtext("gameLink") or ""
        logo = game.findtext("gameLogo") or ""
        hours = (game.findtext("hoursOnRecord") or "").strip()
        if not name or not re.fullmatch(r"https://steamcommunity\.com/app/\d+", link):
            raise ValueError("Invalid game metadata")
        if not re.fullmatch(r"https://[a-z0-9.-]+\.steamstatic\.com/[^\s\"<>]+", logo):
            raise ValueError("Unexpected game image host")
        if not re.fullmatch(r"\d[\d,]*(?:\.\d+)?", hours):
            raise ValueError("Invalid playtime")
        cards.append(
            '<td align="center" width="25%">'
            f'<a href="{escape(link, quote=True)}">'
            f'<img src="{escape(logo, quote=True)}" width="184" alt="{escape(name, quote=True)}">'
            f'</a><br><sub>{escape(name)}</sub>'
            f'<br><sub>{escape(hours)} hrs total</sub></td>'
        )
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    content = '<table><tr>\n' + '\n'.join(cards) + '\n</tr></table>' if cards else '<p><sub>최근 플레이 기록이 없습니다.</sub></p>'
    return (
        f'{START}\n<div align="center">\n\n<h3>🎮 Steam</h3>\n'
        f'<p><sub>최근 플레이 · <a href="{PROFILE}">moveOH ↗</a></sub></p>\n\n'
        f'{content}\n\n<p><sub>Steam 공개 프로필 기준 · 누적 사용 시간 · {timestamp} UTC</sub></p>\n\n'
        f'</div>\n{END}'
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml", type=Path, help="Use a saved response for local checks")
    args = parser.parse_args()
    if args.xml:
        data = args.xml.read_bytes()
    else:
        request = Request(PROFILE + "?xml=1", headers={"User-Agent": "moveoh1004-profile/1.0"})
        with urlopen(request, timeout=30) as response:
            data = response.read()
    section = render(data)
    current = README.read_text()
    if current.count(START) != 1 or current.count(END) != 1:
        raise ValueError("Expected one Steam section")
    before, remainder = current.split(START, 1)
    _, after = remainder.split(END, 1)
    updated = before + section + after
    if updated != current:
        README.write_text(updated)


if __name__ == "__main__":
    main()
