# CGV 판교 디스클로저 데이 예매 오픈 감시기

판교 CGV에서 **디스클로저 데이**의 특정 상영일 예매가 열리는 순간을 감지해 Discord로 알린다.

## 동작 방식

GitHub Actions가 5분마다 [`check.py`](check.py)를 실행한다.

1. 네이버 플레이스의 CGV 판교 상영시간표 페이지를 GET
   (`https://m.place.naver.com/theater/37026678/movie`)
2. HTML에서 대상 영화·극장의 예매 회차 URL을 정규식으로 추출
   - 영화 `movNo=30001188` (디스클로저 데이)
   - 극장 `siteNo=0181` (판교)
3. 감시 날짜(`WATCH_DATES`)가 새로 등장하면 Discord 웹훅으로 알림
4. 이미 알린 날짜는 [`state.json`](state.json)에 기록해 중복 방지

### 왜 CGV가 아니라 네이버인가

CGV 본 사이트(`cgv.co.kr`)는 Cloudflare 봇 차단이 강해 헤드리스 브라우저·데이터센터 IP로는 접근이 막힌다. 네이버 플레이스는 CGV가 공개한 동일 스케줄을 미러링하며, 브라우저·쿠키 없이 단순 GET으로 접근된다.

## 설정

`check.py` 상단 상수로 대상을 바꿀 수 있다.

| 상수 | 의미 | 현재 값 |
|---|---|---|
| `MOV_NO` | CGV 영화 번호 | `30001188` (디스클로저 데이) |
| `SITE_NO` | CGV 극장 번호 | `0181` (판교) |
| `WATCH_DATES` | 감시할 상영일(YYYYMMDD) | `20260612`, `20260613` |

## 시크릿

| 이름 | 설명 |
|---|---|
| `DISCORD_WEBHOOK_URL` | 알림을 받을 Discord 채널 웹훅 URL (repo Settings → Secrets and variables → Actions) |

## 한계

- GitHub Actions cron은 최소 5분 주기이며 부하 시 지연될 수 있다 → "오픈 즉시"가 아니라 "오픈 후 수 분 내" 알림이다.
- 네이버가 데이터센터 IP를 차단하거나 페이지 구조를 바꾸면 동작이 중단될 수 있다. 그 경우 Actions 실행이 실패로 표시된다.
