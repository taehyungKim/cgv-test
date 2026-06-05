#!/usr/bin/env python3
"""판교 CGV '디스클로저 데이' 예매 오픈 감시기.

네이버 플레이스의 CGV 판교 극장 상영시간표 페이지를 가져와서,
대상 영화(movNo)의 특정 날짜(scnYmd) 예매 회차가 등장하면
Discord 웹훅으로 알림을 보낸다. 날짜별로 한 번만 알린다.

CGV 본 사이트는 Cloudflare 봇 차단이 강해 헤드리스/데이터센터 IP로는
접근이 막히지만, 네이버 플레이스는 CGV가 공개한 스케줄을 미러링하며
브라우저/쿠키 없이 단순 GET으로 접근된다. 그래서 이 경로를 쓴다.
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error

# ── 설정 ───────────────────────────────────────────────
# 네이버 플레이스 'CGV 판교' 극장 상영시간표 페이지
THEATER_URL = "https://m.place.naver.com/theater/37026678/movie"
MOV_NO = "30001188"          # 디스클로저 데이 (CGV movNo)
SITE_NO = "0181"             # 판교 (CGV siteNo)
MOVIE_NAME = "디스클로저 데이"
THEATER_NAME = "판교 CGV"
# 감시할 상영일 (YYYYMMDD). 이 영화로 해당 날짜 예매가 열리면 알림.
WATCH_DATES = ["20260612", "20260613"]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
TIMEOUT = 25


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return resp.read().decode("utf-8", "replace")


def open_dates_for_movie(html):
    """HTML에서 대상 영화·판교의 예매 가능 상영일(YYYYMMDD) 집합을 반환."""
    pattern = re.compile(
        r"movNo=" + re.escape(MOV_NO) + r"&scnYmd=(\d{8})&siteNo=" + re.escape(SITE_NO)
    )
    return set(pattern.findall(html))


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("alerted", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_state(alerted):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"alerted": sorted(alerted)}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def fmt_date(ymd):
    return f"{int(ymd[4:6])}/{int(ymd[6:8])}"


def send_discord(webhook, content):
    body = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"Discord HTTP {resp.status}")


def main():
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("ERROR: DISCORD_WEBHOOK_URL 환경변수가 없습니다.", file=sys.stderr)
        return 2

    try:
        html = fetch_html(THEATER_URL)
    except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
        print(f"ERROR: 네이버 페이지 조회 실패: {e}", file=sys.stderr)
        return 1

    # 페이지가 정상인지 최소 검증 (차단/구조변경 조기 감지)
    if SITE_NO not in html and "판교" not in html:
        print("ERROR: 예상 마커(siteNo/판교)가 없습니다. 차단 또는 구조 변경 의심.",
              file=sys.stderr)
        return 1

    open_dates = open_dates_for_movie(html)
    print(f"[info] {MOVIE_NAME} @{THEATER_NAME} 현재 예매가능: {sorted(open_dates) or '없음'}")

    alerted = load_state()
    newly = [d for d in WATCH_DATES if d in open_dates and d not in alerted]

    if not newly:
        print("[info] 새로 열린 감시 날짜 없음.")
        return 0

    for ymd in newly:
        msg = (
            f"🎬 **{THEATER_NAME} '{MOVIE_NAME}' {fmt_date(ymd)} 예매 오픈 감지!**\n"
            f"바로 예매: {THEATER_URL}"
        )
        send_discord(webhook, msg)
        alerted.add(ymd)
        print(f"[alert] {ymd} 알림 전송 완료.")

    save_state(alerted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
