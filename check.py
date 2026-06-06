#!/usr/bin/env python3
"""판교 CGV '디스클로저 데이' 새 회차 감시기.

네이버 플레이스의 CGV 판교 극장 상영시간표 페이지를 가져와서,
대상 영화(movNo)의 감시 날짜에 새 회차(상영 시작시각)가 생기면
Discord 웹훅으로 그 시각들을 알린다. 이미 본 시각은 재알림하지 않는다.

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
# 감시할 상영일 (YYYYMMDD). 해당 날짜에 새 회차(시간대)가 생기면 알린다.
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


def showtimes_for(html, ymd):
    """대상 영화·판교·해당 날짜의 예매 회차 시작시각(HH:MM) 집합.
    ScheduleInfo의 ticketPcUrl(영화·날짜·극장 일치) 값 종료 직후 rtime을 매칭."""
    pattern = re.compile(
        r"movNo=" + re.escape(MOV_NO) + r"&scnYmd=" + re.escape(ymd) +
        r"&siteNo=" + re.escape(SITE_NO) + r'[^"]*","rtime":"(\d{1,2}:\d{2})"'
    )
    return set(pattern.findall(html))


def load_state():
    """날짜별로 지금까지 본 회차 시각 집합을 반환."""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {k: set(v) for k, v in data.get("showtimes", {}).items()}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(showtimes):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"showtimes": {k: sorted(v) for k, v in showtimes.items()}},
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

    seen = load_state()
    sent = 0

    for ymd in WATCH_DATES:
        cur_times = showtimes_for(html, ymd)
        seen_times = seen.get(ymd, set())
        new_times = cur_times - seen_times
        d = fmt_date(ymd)
        print(f"[info] {MOVIE_NAME} {d}: 회차(현재)={sorted(cur_times) or '없음'} "
              f"신규={sorted(new_times) or '없음'}")

        # 새 회차(시간대)가 생겼을 때만 알린다.
        if new_times:
            times_str = ", ".join(sorted(new_times))
            send_discord(
                webhook,
                f"🎬 **{THEATER_NAME} '{MOVIE_NAME}' {d} 새 회차!** ({times_str})\n"
                f"바로 예매: {THEATER_URL}",
            )
            seen[ymd] = seen_times | cur_times  # 합집합 보관(재등장 재알림 방지)
            sent += 1
            print(f"[alert] {ymd} 새 회차 알림 전송: {times_str}")

    if sent:
        save_state(seen)
    else:
        print("[info] 새 회차 없음.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
