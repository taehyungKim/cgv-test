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
MOV_NO = "30001188"          # 디스클로저 데이 (CGV movNo) — 예매 회차 매칭용
MOVIE_CODE = "252458"        # 디스클로저 데이 (네이버 movieCode) — 라인업 등재 매칭용
SITE_NO = "0181"             # 판교 (CGV siteNo)
MOVIE_NAME = "디스클로저 데이"
THEATER_NAME = "판교 CGV"
# 감시할 상영일 (YYYYMMDD).
# 두 단계로 감지: (1) 라인업 등재(상영 예정 추가) (2) 실제 예매 회차 오픈.
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


def bookable_dates(html):
    """대상 영화·판교의 '실제 예매 회차'가 있는 상영일(YYYYMMDD) 집합."""
    pattern = re.compile(
        r"movNo=" + re.escape(MOV_NO) + r"&scnYmd=(\d{8})&siteNo=" + re.escape(SITE_NO)
    )
    return set(pattern.findall(html))


def listed_dates(html):
    """대상 영화가 '상영 라인업(MovieTime)'에 등재된 상영일(YYYYMMDD) 집합.
    예매 회차보다 먼저 뜨는 경우가 있어 예매 임박 신호로 쓴다.
    네이버 데이터의 date는 'YYYY-MM-DD' 형식이라 YYYYMMDD로 변환한다."""
    dashed = set()
    # movieCode 기반 (필드 순서: movieCode, date, name)
    dashed |= set(re.findall(
        r'"movieCode":"' + re.escape(MOVIE_CODE) + r'","date":"(\d{4}-\d{2}-\d{2})"', html))
    # 영화 이름 기반 (백업)
    dashed |= set(re.findall(
        r'"date":"(\d{4}-\d{2}-\d{2})","name":"' + re.escape(MOVIE_NAME) + r'"', html))
    return {d.replace("-", "") for d in dashed}


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {
            "listed": set(data.get("listed", [])),
            "bookable": set(data.get("bookable", [])),
        }
    except (FileNotFoundError, json.JSONDecodeError):
        return {"listed": set(), "bookable": set()}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"listed": sorted(state["listed"]), "bookable": sorted(state["bookable"])},
            f, ensure_ascii=False, indent=2,
        )
        f.write("\n")


def fmt_date(ymd):
    return f"{int(ymd[4:6])}/{int(ymd[6:8])}"


def send_discord(webhook, content):
    body = json.dumps({"content": content}).encode("utf-8")
    # User-Agent 필수: 기본 'Python-urllib'는 Discord가 403으로 차단한다.
    req = urllib.request.Request(
        webhook,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "cgv-watch (https://github.com/taehyungKim/cgv-test, 1.0)",
        },
        method="POST",
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

    booking = bookable_dates(html)
    listing = listed_dates(html)
    print(f"[info] {MOVIE_NAME} @{THEATER_NAME} 라인업 등재: {sorted(listing) or '없음'} "
          f"/ 예매가능: {sorted(booking) or '없음'}")

    state = load_state()
    sent = 0

    for ymd in WATCH_DATES:
        is_listed = ymd in listing
        is_bookable = ymd in booking

        # (2) 실제 예매 가능 — 가장 중요한 알림. 날짜별 1회.
        if is_bookable and ymd not in state["bookable"]:
            send_discord(
                webhook,
                f"🎬 **{THEATER_NAME} '{MOVIE_NAME}' {fmt_date(ymd)} 예매 가능!**\n"
                f"바로 예매: {THEATER_URL}",
            )
            state["bookable"].add(ymd)
            state["listed"].add(ymd)  # 예매 가능하면 등재 알림은 생략
            sent += 1
            print(f"[alert] {ymd} 예매가능 알림 전송.")
            continue

        # (1) 라인업 등재 — 예매 임박 조기 알림. 날짜별 1회.
        if is_listed and ymd not in state["listed"]:
            send_discord(
                webhook,
                f"📋 **{THEATER_NAME} '{MOVIE_NAME}' {fmt_date(ymd)} 상영 라인업 등재!** "
                f"(예매 임박 — 곧 회차가 열립니다)\n"
                f"확인: {THEATER_URL}",
            )
            state["listed"].add(ymd)
            sent += 1
            print(f"[alert] {ymd} 라인업 등재 알림 전송.")

    if sent:
        save_state(state)
    else:
        print("[info] 새 알림 없음.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
