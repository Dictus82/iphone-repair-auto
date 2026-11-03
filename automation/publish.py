"""승인된 게시물을 예약 시간에 Instagram에 게시합니다 (GitHub Actions에서 실행).

게시 조건 (모두 만족해야 함)
1. post.toml의 approved = true
2. 예약 시간(KST)이 지났고, 지난 지 LATE_LIMIT_HOURS 이내
3. result.json이 없음 (한 번 처리한 게시물은 다시 올리지 않음)
4. validate.py 검사 통과
5. 실제 게시 모드: --live 옵션 + 저장소 변수 PUBLISH_ENABLED = true

사용법
  python automation/publish.py                 # 미리보기(기본): 게시 대상만 출력
  python automation/publish.py --now "2026-11-10 19:05"   # 특정 시각 기준 미리보기
  python automation/publish.py --live --commit # 실제 게시 (GitHub Actions 전용)

필요한 환경 변수 (실제 게시 때만, GitHub Secrets에 저장 - 파일·대화에 쓰지 않음)
  IG_ACCESS_TOKEN  Instagram 장기 액세스 토큰
  IG_LOGIN_TYPE    unified(Unified login 토큰) 또는 instagram(기본)
  IG_USER_ID       Instagram 계정 ID. unified는 필수, instagram은 없으면 "me"
  IG_API_VERSION   (선택) 기본 v26.0
  MEDIA_BASE_URL   (선택) 이미지 공개 주소. 없으면 GitHub raw 주소 사용
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from common import (CHECK_NEEDED, FAILED, MISSED, PUBLISHED, PUBLISHING,
                    fmt_kst, load_posts, now_kst, parse_kst)
from validate import validate_post

LATE_LIMIT_HOURS = 3      # 예약 시간보다 3시간 넘게 늦으면 올리지 않음
MAX_POSTS_PER_RUN = 3
POLL_SECONDS, POLL_TRIES = 15, 20   # 컨테이너 준비 확인 (최대 약 5분)
REEL_POLL_TRIES = 48                # 영상은 처리 시간이 길어 최대 약 12분


class ApiError(Exception):
    pass


class Instagram:
    """IG_LOGIN_TYPE
    - unified   : Unified login (시스템 사용자 토큰) → graph.facebook.com, IG_USER_ID 필수
                  (이 토큰에서 'me'는 인스타 계정이 아니라 시스템 사용자를 뜻함)
    - instagram : Instagram 로그인 토큰 → graph.instagram.com, IG_USER_ID 없으면 'me'
    """

    def __init__(self, require_user=True):
        self.token = os.environ.get("IG_ACCESS_TOKEN", "")
        if not self.token:
            raise SystemExit("IG_ACCESS_TOKEN이 없습니다 (GitHub Secrets 설정 필요)")
        self.login = (os.environ.get("IG_LOGIN_TYPE") or "instagram").strip().lower()
        if self.login not in ("unified", "instagram"):
            raise SystemExit("IG_LOGIN_TYPE은 unified 또는 instagram")
        version = os.environ.get("IG_API_VERSION") or "v26.0"
        host = "graph.facebook.com" if self.login == "unified" else "graph.instagram.com"
        self.base = f"https://{host}/{version}"
        self.user = (os.environ.get("IG_USER_ID") or "").strip()
        if not self.user:
            if self.login == "unified" and require_user:
                raise SystemExit("Unified login은 IG_USER_ID가 필요합니다 ('연결 확인' 실행으로 확인)")
            self.user = "me" if self.login == "instagram" else ""

    def call(self, method, path, **params):
        params["access_token"] = self.token
        data = urllib.parse.urlencode(params)
        url = f"{self.base}/{path}"
        if method == "GET":
            req = urllib.request.Request(f"{url}?{data}")
        else:
            req = urllib.request.Request(url, data=data.encode(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            # 오류 메시지에 토큰이 들어가지 않도록 응답 본문의 error만 사용
            try:
                err = json.loads(e.read()).get("error", {})
                msg = f"{err.get('code')}/{err.get('error_subcode')}: {err.get('message')}"
            except Exception:
                msg = f"HTTP {e.code}"
            raise ApiError(msg) from None
        except urllib.error.URLError as e:
            raise ApiError(f"연결 오류: {e.reason}") from None

    def create(self, **params):
        return self.call("POST", f"{self.user}/media", **params)["id"]

    def wait_ready(self, container_id, tries=POLL_TRIES):
        for _ in range(tries):
            code = self.call("GET", container_id, fields="status_code").get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise ApiError(f"컨테이너 상태 {code}")
            time.sleep(POLL_SECONDS)
        raise ApiError("컨테이너 준비 시간 초과")

    def publish(self, container_id):
        return self.call("POST", f"{self.user}/media_publish", creation_id=container_id)["id"]

    def permalink(self, media_id):
        try:
            return self.call("GET", media_id, fields="permalink").get("permalink", "")
        except ApiError:
            return ""


def file_url(post, name):
    base = os.environ.get("MEDIA_BASE_URL")
    if not base:
        repo, sha = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_SHA")
        if not (repo and sha):
            raise SystemExit("이미지 공개 주소를 만들 수 없습니다 (GitHub Actions 밖에서 실행됨)")
        base = f"https://raw.githubusercontent.com/{repo}/{sha}"
    return f"{base.rstrip('/')}/content/posts/{post.id}/{urllib.parse.quote(name)}"


def media_urls(post):
    return [file_url(post, p.name) for p in post.media]


def git_save(post, message):
    """result.json을 저장소에 커밋·푸시. 실패하면 예외 (게시 전 단계라면 게시 중단)."""
    subprocess.run(["git", "add", str(post.result_path)], check=True)
    subprocess.run(["git", "commit", "-m", message], check=True)
    for _ in range(3):
        if subprocess.run(["git", "push"]).returncode == 0:
            return
        subprocess.run(["git", "pull", "--rebase"], check=False)
    raise RuntimeError("git push 실패")


def publish_post(ig, post, commit):
    urls = media_urls(post)
    caption = post.caption
    tries = POLL_TRIES
    if post.type == "image":
        container = ig.create(image_url=urls[0], caption=caption)
    elif post.type == "reel":
        params = {"media_type": "REELS", "video_url": urls[0], "caption": caption,
                  "share_to_feed": "true" if post.meta.get("share_to_feed", True) else "false"}
        if post.meta.get("cover"):
            params["cover_url"] = file_url(post, post.meta["cover"])
        container = ig.create(**params)
        tries = REEL_POLL_TRIES
    else:
        children = []
        for u in urls:
            cid = ig.create(image_url=u, is_carousel_item="true")
            ig.wait_ready(cid)
            children.append(cid)
        container = ig.create(media_type="CAROUSEL", children=",".join(children),
                              caption=caption)
    ig.wait_ready(container, tries)

    # 게시 직전 상태를 먼저 기록 → 기록이 안 되면 게시하지 않음 (중복 게시 방지)
    started = fmt_kst(now_kst())
    post.save_result({"status": PUBLISHING, "container_id": container,
                      "started_at_kst": started})
    if commit:
        git_save(post, f"게시 시작: {post.id}")

    try:
        media_id = ig.publish(container)
    except ApiError as e:
        post.save_result({"status": CHECK_NEEDED, "container_id": container,
                          "started_at_kst": started, "error": str(e),
                          "note": "게시 요청 중 오류. 인스타 앱에서 올라갔는지 확인 후 처리"})
        raise
    post.save_result({"status": PUBLISHED, "media_id": media_id,
                      "permalink": ig.permalink(media_id),
                      "scheduled_at_kst": post.scheduled_text,
                      "published_at_kst": fmt_kst(now_kst())})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="실제 게시")
    ap.add_argument("--commit", action="store_true", help="결과를 git에 커밋·푸시")
    ap.add_argument("--now", help="기준 시각 (KST, 미리보기 전용)")
    args = ap.parse_args()

    live = args.live and os.environ.get("PUBLISH_ENABLED", "").lower() == "true"
    if args.live and not live:
        print("PUBLISH_ENABLED가 true가 아니므로 미리보기로만 실행합니다.")
    if args.now and live:
        raise SystemExit("--now는 미리보기에서만 사용할 수 있습니다")
    now = parse_kst(args.now) if args.now else now_kst()
    print(f"기준 시각(KST): {fmt_kst(now)}  모드: {'실제 게시' if live else '미리보기'}")

    due = []
    for p in load_posts():
        if not p.approved or p.result:
            continue
        try:
            when = p.scheduled_at
        except ValueError:
            continue  # 형식 오류는 validate에서 표시
        if when and when <= now:
            due.append((when, p))
    due.sort(key=lambda x: x[0])

    if not due:
        print("게시할 게시물이 없습니다.")
        return 0

    ig = Instagram() if live else None
    had_error = False
    for when, post in due[:MAX_POSTS_PER_RUN]:
        label = f"{post.id} (예약 {fmt_kst(when)})"
        if (now - when).total_seconds() > LATE_LIMIT_HOURS * 3600:
            print(f"- 시간 초과, 게시 안 함: {label}")
            if live:
                post.save_result({"status": MISSED, "scheduled_at_kst": post.scheduled_text,
                                  "checked_at_kst": fmt_kst(now),
                                  "note": "예약 시간을 다시 정하고 result.json을 지우면 재예약"})
                if args.commit:
                    git_save(post, f"시간 초과: {post.id}")
            continue

        errors, _ = validate_post(post)
        if errors:
            had_error = True
            print(f"- 검사 실패, 게시 안 함: {label}")
            for e in errors:
                print(f"   ✗ {e}")
            if live:
                post.save_result({"status": FAILED, "errors": errors,
                                  "checked_at_kst": fmt_kst(now)})
                if args.commit:
                    git_save(post, f"게시 실패(검사): {post.id}")
            continue

        if not live:
            print(f"- 게시 대상: {label} / {post.type} {len(post.media)}장 / {post.title}")
            continue

        try:
            publish_post(ig, post, args.commit)
            print(f"- 게시 완료: {label} {post.result.get('permalink', '')}")
        except ApiError as e:
            had_error = True
            print(f"- 게시 실패: {label} - {e}")
            if post.status != CHECK_NEEDED:
                post.save_result({"status": FAILED, "error": str(e),
                                  "checked_at_kst": fmt_kst(now_kst())})
        if args.commit:
            git_save(post, f"게시 결과: {post.id} ({post.status})")

    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
