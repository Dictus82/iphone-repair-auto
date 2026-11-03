# 정보형 릴스 자동 제작 (아이폰 뉴스·정보 + 무료 스톡 참고 영상)

## 흐름

```
1 주제 수집      python automation/topic_scout.py          → outputs/topics/<날짜>.md (후보·근거·제외 사유)
2 주제 선정·사실 확인·대본 (Claude)                         → outputs/reels/<주제>/reel.toml, caption.txt
3 스톡 영상      python automation/stock_library.py search "<영어 검색어>"   (공식 API)
                 python automation/stock_library.py frames <ID>            (검수용 장면)
                 python automation/stock_library.py review <ID> ok "로고·얼굴 없음"
4 제작           python automation/make_stock_reel.py outputs/reels/<주제>/reel.toml
                 → content/posts/<ID>/ (reel.mp4, cover.jpg, caption.txt, credits.json, post.toml 미승인)
5 검사·업로드    python automation/validate.py → git push
6 승인 (사장님)  post.toml: scheduled_at + approved = true  → 클라우드가 예약 시간에 게시
```

**주제만 말하면 됩니다.** 예: "‘iOS 27.2 업데이트 해야 할까’로 릴스 만들어줘" 또는 "이번 주 주제 골라서 만들어줘".
Claude가 2~5단계를 진행하고, 사장님은 영상·캡션을 확인해 승인만 합니다.

## 주제 선정 기준
- 수집 범위: 신형 아이폰(발표·출시·가격·변경점), iOS(업데이트·새 기능·지원 기종), 배터리·발열·충전·통신·카메라 문제,
  보안 업데이트·서비스 프로그램·리콜, 중고폰·개인정보·사용법, 비교·구매 정보
- 점수: 최신성 + 소비자 영향 + 출처 신뢰 + 검색 관심도(네이버 데이터랩, 키가 있을 때만) − 기존 콘텐츠 중복
- **출처 유형 구분:** 공식 / 언론 / 사용자 제보 보도 / 루머·전망 → 제보·루머는 기본 제외
- 보도 날짜와 사건 날짜를 따로 기록하고, **한국 출시·가격·적용 여부는 apple.com/kr 등에서 따로 확인**
- 검색 관심도를 확인하지 못하면 "미확인"으로 적고, 인기·검색량 표현을 쓰지 않음
- 일부 사용자 제보를 전체 기종 결함처럼 표현하지 않음

## 대본·영상 규칙
- 기사 문장·사진·방송 영상은 가져오지 않습니다. 사실만 확인해 자체 문장으로 씁니다.
- 20초 안팎: 궁금증을 끄는 첫 문장 → 핵심 정보 1~2개 → 짧은 마무리 → 매장 안내 화면
- 화면 상단에 **"이해를 돕기 위한 참고 영상"** 표시. 신제품 주제에 다른 기종 영상을 쓰면
  `label = "참고 영상 · 실제 신제품 모습 아님"`으로 바꿉니다.
- 스톡 영상은 로고·상표·식별 가능한 얼굴이 없는 것만 `review ok` 처리합니다 (Pexels·Pixabay 약관: 상표가 보이는 콘텐츠의 상업적 이용 제한, 인물이 보증하는 것처럼 쓰면 안 됨).
- 음악: 사용 권한이 확인된 경우에만 넣습니다 (현재 없음).
- 출처·확인 날짜·선정 근거는 `credits.json`에 자동 기록되고, 출처가 공식·언론이 아니면 검사에서 막힙니다.

## spec(reel.toml) 형식
`outputs/reels/battery-drain/reel.toml` 참고. 필수: `post_id`, `lines`(나레이션=자막), `end_line`, `end_card`,
`clips`(검수 ok 영상 ID), `[selection]`(선정 근거), `[[facts]]`(주장·출처 유형·URL·확인 날짜).

## 원본 보관
- 스톡 원본: `stock/` (공개 저장소에 올라가지 않음), 권리 기록: `stock/library.json`
  (원본 URL, 제작자, 라이선스 URL, 약관 확인 날짜, 검수 결과)
- 완성 릴스(편집·자막·나레이션이 더해진 영상)만 `content/posts/`로 올라갑니다.

---

## API 키 발급 (무료) - 키는 대화창·프로젝트 파일에 넣지 않습니다

키는 **Windows 사용자 환경 변수**에 직접 등록합니다.
- 시작 메뉴에서 "**계정의 환경 변수 편집**"을 검색해 엽니다.
- 위쪽 "사용자 변수" → **새로 만들기** → 변수 이름과 값(키)을 입력합니다 → **확인**.

### Pexels (필수 - 스톡 영상)
1. https://www.pexels.com 에서 가입 또는 로그인
2. https://www.pexels.com/api/ → **Your API Key** (또는 Get Started)
3. 사용 목적 입력 예: "Short info videos (Instagram Reels) for my local phone repair shop. A few stock videos per week."
4. 약관 동의 → 화면에 키가 바로 표시됨
5. 환경 변수 이름: `PEXELS_API_KEY`
- 무료 한도: 시간당 200회, 월 20,000회 (검색 1회 = 1회)

### Pixabay (선택 - 추가 스톡 영상)
1. https://pixabay.com/accounts/register/ 가입 → 로그인
2. https://pixabay.com/api/docs/ 의 Parameters 표 `key` 줄에 본인 키가 표시됨
3. 환경 변수 이름: `PIXABAY_API_KEY`

### 네이버 (선택 - 뉴스 수집·검색 관심도)
1. https://developers.naver.com → 로그인 → **Application → 애플리케이션 등록**
2. 사용 API: **검색**, **데이터랩 (검색어트렌드)** 추가
3. 비로그인 오픈 API 서비스 환경: **WEB 설정**, 웹 서비스 URL `http://localhost`
4. 등록 후 **Client ID**, **Client Secret** 확인
5. 환경 변수 이름: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
- 무료 한도: 검색 하루 25,000회, 데이터랩 하루 1,000회
- 데이터랩 값은 기간 내 최대값을 100으로 한 **상대값**이며 실제 검색량이 아닙니다.

## 비용
| 항목 | 비용 |
|---|---|
| Pexels·Pixabay API, 스톡 영상 | 0원 |
| 네이버 검색·데이터랩 API | 0원 |
| 나레이션 (Windows 내장 음성) | 0원 |
| 영상 편집(ffmpeg), 클라우드 게시 | 0원 |
| (선택) 더 자연스러운 음성: Google Cloud TTS | 무료 한도 월 100만 자 안에서는 0원 예상, 결제 카드 등록 필요 |
| (선택) ElevenLabs Starter | 월 약 $6 |
