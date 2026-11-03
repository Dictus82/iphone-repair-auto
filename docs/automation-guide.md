# 인스타그램 예약 자동 게시 안내 (마석역 폰수리)

> 이 저장소는 **아이폰 수리센터 전용**입니다. 가죽공방(leather-academy)은 별도 저장소·별도 토큰으로 운영합니다.
> 비밀번호·토큰은 대화창이나 파일에 붙여넣지 않습니다. GitHub의 Secrets 화면에만 입력합니다.

## 전체 흐름

```
주제 선정 → 글·이미지 제작 → 초안 등록 → 사장님 승인 → 예약 시간에 자동 게시 → 결과 기록
 (PC: Claude Code)          (approved=false)  (approved=true)  (클라우드: GitHub Actions)
```

- 게시는 클라우드(GitHub Actions)에서 실행되므로 **PC를 꺼도 게시됩니다.**
- 제작(주제·글·이미지)은 현재 PC의 Claude Code에서 합니다. 클라우드 제작은 4단계에서 결정합니다.
- 실행 간격은 15분이고, GitHub 사정으로 **예약 시간보다 몇 분~수십 분 늦게** 올라갈 수 있습니다.
- 예약 시간보다 3시간 넘게 늦어지면 올리지 않고 "시간 초과"로 기록합니다.

## 폴더 구조

```
content/posts/<게시물ID>/
  post.toml     제목, 예약 시간(KST), 승인 여부, 이미지 목록  ← 사람이 수정
  caption.txt   캡션
  01.jpg ...    이미지 (JPEG)
  result.json   게시 결과                                      ← 프로그램이 기록
content/SCHEDULE.md   전체 현황표 (자동 갱신)
automation/           게시 프로그램 (사업 정보 없음)
.github/workflows/    클라우드 실행 설정
```

## 승인과 예약 방법

1. Claude가 초안을 만듭니다 (`approved = false`).
2. 사장님이 이미지와 캡션을 확인합니다.
3. `post.toml`에서 두 줄을 바꿉니다.
   ```toml
   scheduled_at = "2026-11-10 19:00"   # 한국 시간
   approved = true
   ```
   - GitHub 웹/앱에서 파일 연필 아이콘 → 수정 → Commit changes
   - 또는 Claude에게 "screen-info, 11월 10일 저녁 7시로 승인"이라고 말하면 대신 수정합니다.
     (**사장님이 직접 승인을 말한 경우에만** 바꿉니다)
4. 취소: 예약 시간 전에 `approved = false`로 되돌립니다.
5. 실패한 게시물을 다시 예약: 원인을 고치고 `result.json`을 지운 뒤 새 시간으로 바꿉니다.
6. 승인 후 이미지나 캡션을 고쳤다면 다시 확인하고 승인합니다.

## 자동 검사 (승인해도 아래에 걸리면 게시하지 않음)

- 이미지: JPEG, 비율 4:5~1.91:1, 8MB 이하, 여러 장 게시(carousel)는 2~20장
- 캡션: 2,200자 이하, 해시태그 30개 이하
- 확인 전 사용 금지 표현: 정품, 정식 부품, 공인, Apple 공식, 최저가, 가장 저렴, 100%, 무조건, 금액(○○원)
  → 사실로 확인되면 `confirmed_terms`에 넣어야 통과
- 실제 수리 사례(`kind = "case"`): 고객 동의·개인정보 가림 확인 항목이 `true`여야 통과

## 단계별 진행

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 승인 → 예약 자동 게시 (사진 카드뉴스) | 코드 완성, 계정 연결 전 |
| 2 | 실제 사진 사용 (사장님이 찍고 가린 사진만) | 연결 전 |
| 3 | 영상(릴스) 제작·게시 | 연결 전 (제작 도구 선택 필요) |
| 4 | 주제 선정·제작도 클라우드에서 | 연결 전 (비용 확인 후 결정) |

- 실제 수리 사례와 사진은 사장님이 제공한 것만 씁니다. AI로 수리 전후 사진을 만들지 않습니다.

## 비용

| 항목 | 비용 |
|---|---|
| GitHub 공개 저장소 + Actions 실행 | 0원 |
| Meta(Instagram) 개발자 앱·게시 API | 0원 |
| GitHub 비공개 저장소 | 무료 실행 시간(월 2,000분)을 넘을 수 있고, 이미지 공개 주소를 따로 마련해야 함 → 권장하지 않음 |
| 2~4단계 (사진·영상 도구, 클라우드 제작) | 도구를 고를 때 금액을 먼저 안내 |

**공개 저장소 주의:** 저장소 내용(초안, 캡션, 이미지)을 누구나 볼 수 있습니다. 토큰은 Secrets에 있어 보이지 않습니다.
개인정보를 가리지 않은 사진은 절대 올리지 않습니다 (`photos/`, `outputs/` 폴더는 업로드에서 제외됨).

---

## 계정 연결 안내 (사장님이 직접 하는 단계)

> 메뉴 이름은 Meta·GitHub 화면 개편으로 조금 다를 수 있습니다. 막히면 화면에 보이는 내용을 말씀해 주세요.

### 1단계. 인스타그램 프로페셔널 계정 확인
1. 인스타그램 앱 → 프로필 → 오른쪽 위 ☰
2. **계정 유형 및 도구** → **프로페셔널 계정으로 전환** (이미 비즈니스/크리에이터면 건너뜀)
3. 비즈니스 → 카테고리 선택 (예: 휴대폰 수리)

### 2단계. GitHub 저장소 만들기
1. https://github.com 가입 또는 로그인
2. https://github.com/new
3. Repository name: `iphone-repair-instagram` (예시), **Public**, 다른 옵션은 체크하지 않음 → **Create repository**
4. 만든 저장소 주소를 Claude에게 알려주세요. 업로드 명령은 Claude가 실행하고,
   로그인 창이 뜨면 **브라우저에서 직접 로그인**합니다 (비밀번호를 대화에 쓰지 않음).

### 3단계. Meta 개발자 앱 만들기
1. https://developers.facebook.com → 페이스북 계정으로 로그인 → 개발자 등록(처음이면)
2. **내 앱** → **앱 만들기**
3. 사용 사례: **Instagram에서 메시지 및 콘텐츠 관리** 선택
4. 앱 이름 예: `iphone-repair-publisher` → 만들기

### 4단계. 인스타 계정 연결과 토큰 만들기
1. 앱 대시보드 → **Instagram** → **Instagram 로그인을 통한 API 설정**
2. 권한에 `instagram_business_basic`, `instagram_business_content_publish`가 있는지 확인
3. **액세스 토큰 생성** 영역 → **계정 추가** → 마석역 폰수리 인스타 계정으로 로그인·허용
   - 테스터 초대가 필요하다고 나오면: 앱 대시보드 **앱 역할 → 역할 → Instagram 테스터 추가**,
     그다음 인스타그램 앱(또는 웹) **설정 → 웹사이트 권한 → 앱 및 웹사이트 → 테스터 초대**에서 수락
4. 계정 옆 **토큰 생성** → 토큰을 복사 (이 창은 닫지 말고 바로 5단계로)

### 5단계. GitHub에 토큰 저장
1. GitHub 저장소 → **Settings** → **Secrets and variables** → **Actions**
2. **Secrets** 탭 → **New repository secret**
   - Name: `IG_ACCESS_TOKEN` / Secret: 복사한 토큰 붙여넣기 → **Add secret**
3. **Variables** 탭 → **New repository variable**
   - Name: `PUBLISH_ENABLED` / Value: `false` (실제 게시는 아직 꺼둠)

### 6단계. 토큰 자동 갱신 권한 (권장)
토큰은 60일마다 만료되므로 매주 자동 갱신합니다. 새 토큰을 자동 저장하려면:
1. https://github.com/settings/personal-access-tokens → **Generate new token** (Fine-grained)
2. Repository access: **Only select repositories** → 이 저장소만
3. Permissions → Repository permissions → **Secrets: Read and write**
4. 만료 기간 선택 (최대 1년, 만료 전 다시 발급) → 생성 → 복사
5. 5단계와 같은 화면에서 Secret 추가: Name `GH_SECRETS_TOKEN`

### 7단계. 연결 확인 (실제 게시 없음)
1. 저장소 → **Actions** → **토큰 갱신** → **Run workflow** → 초록색이면 성공 (남은 기간 표시)
2. **예약 게시** → **Run workflow** (실제 게시 체크 해제) → 게시 대상 목록 확인

### 8단계. 예약 실행과 실제 게시 켜기 (사장님이 결정할 때만)
처음 업로드할 때는 두 가지가 모두 꺼져 있습니다.
1. **예약 실행:** `.github/workflows/publish.yml`과 `refresh-token.yml`의 `schedule` 두 줄 앞 `#`을 지움 (Claude에게 요청 가능)
2. **실제 게시:** Variables의 `PUBLISH_ENABLED`를 `true`로 바꿈
- 1만 켜면 15분마다 미리보기만 하고, 1과 2를 모두 켜야 승인된 게시물이 예약 시간에 올라갑니다.
- 끄려면 `PUBLISH_ENABLED`를 `false`로 바꿉니다.

## 문제가 생겼을 때
- GitHub이 실패한 실행을 메일로 알려줍니다. **Actions** 탭에서 빨간 실행을 열면 이유가 한국어로 나옵니다.
- `확인 필요`(check_needed) 상태: 게시 요청 중 오류가 났습니다. 인스타 앱에서 실제로 올라갔는지 확인한 뒤 Claude에게 알려주세요.
- 공개 저장소에서 60일 동안 변경이 없으면 GitHub이 예약 실행을 멈춥니다. 게시가 계속되면 자동으로 기록이 남아 유지됩니다.
