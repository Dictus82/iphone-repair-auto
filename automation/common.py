"""게시물 관리 공통 기능 (사업 정보 없음 - 다른 계정 저장소에도 그대로 복사해 쓸 수 있음).

게시물 한 개 = content/posts/<게시물ID>/ 폴더 하나
- post.toml   : 사람이 쓰는 파일 (제목, 예약 시간, 승인 여부, 이미지 목록)
- caption.txt : 인스타그램 캡션
- 01.jpg ...  : 게시 이미지 (JPEG만 가능)
- result.json : 게시 결과 (자동 게시 프로그램만 씀, 사람은 수정하지 않음)

시간은 모두 한국 시간(KST, UTC+9, 서머타임 없음)입니다.
"""
import json
import re
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9), "KST")
ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "content" / "posts"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TIME_FORMAT = "%Y-%m-%d %H:%M"

# 결과 상태
PUBLISHED = "published"        # 게시 완료
PUBLISHING = "publishing"      # 게시 직전 기록 (이 상태로 남으면 확인 필요)
FAILED = "failed"              # 게시 전 실패 (인스타에 올라가지 않음)
MISSED = "missed"              # 예약 시간을 너무 지나서 게시하지 않음
CHECK_NEEDED = "check_needed"  # 게시 요청 중 오류 - 인스타 앱에서 직접 확인 필요

STATUS_KO = {
    "draft": "초안(미승인)",
    "approved": "승인·예약 대기",
    PUBLISHED: "게시 완료",
    PUBLISHING: "게시 중/확인 필요",
    FAILED: "실패",
    MISSED: "시간 초과(미게시)",
    CHECK_NEEDED: "확인 필요",
}


def now_kst():
    return datetime.now(KST)


def parse_kst(text):
    return datetime.strptime(text.strip(), TIME_FORMAT).replace(tzinfo=KST)


def fmt_kst(dt):
    return dt.astimezone(KST).strftime(TIME_FORMAT)


class Post:
    def __init__(self, folder: Path):
        self.folder = folder
        self.id = folder.name
        with open(folder / "post.toml", "rb") as f:
            self.meta = tomllib.load(f)

    @property
    def title(self):
        return self.meta.get("title", "")

    @property
    def type(self):
        return self.meta.get("type", "")

    @property
    def approved(self):
        return self.meta.get("approved") is True

    @property
    def scheduled_text(self):
        return str(self.meta.get("scheduled_at", "")).strip()

    @property
    def scheduled_at(self):
        """예약 시간(KST). 비어 있으면 None, 형식이 틀리면 ValueError."""
        if not self.scheduled_text:
            return None
        return parse_kst(self.scheduled_text)

    @property
    def media(self):
        return [self.folder / name for name in self.meta.get("media", [])]

    @property
    def caption_path(self):
        return self.folder / self.meta.get("caption_file", "caption.txt")

    @property
    def caption(self):
        return self.caption_path.read_text(encoding="utf-8-sig").strip()

    @property
    def result_path(self):
        return self.folder / "result.json"

    @property
    def result(self):
        if self.result_path.exists():
            return json.loads(self.result_path.read_text(encoding="utf-8"))
        return {}

    @property
    def status(self):
        if self.result.get("status"):
            return self.result["status"]
        return "approved" if self.approved else "draft"

    def save_result(self, data):
        self.result_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_posts():
    if not POSTS_DIR.exists():
        return []
    return [Post(d) for d in sorted(POSTS_DIR.iterdir())
            if d.is_dir() and (d / "post.toml").exists()]
