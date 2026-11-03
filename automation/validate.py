"""게시물 검사. 승인 전 확인용이며, 자동 게시 직전에도 다시 검사합니다.

사용법: python automation/validate.py [게시물ID ...]
오류가 있으면 종료 코드 1.
"""
import re
import shutil
import subprocess
import sys

from common import ID_RE, Post, load_posts

# Instagram 공식 게시 API 기준 (2026-11 확인)
CAPTION_MAX = 2200
HASHTAG_MAX = 30
CAROUSEL_MIN, CAROUSEL_MAX = 2, 20
IMAGE_MAX_BYTES = 8 * 1024 * 1024
RATIO_MIN, RATIO_MAX = 4 / 5, 1.91      # 세로 4:5 ~ 가로 1.91:1
SUPPORTED_TYPES = ("image", "carousel", "reel")
# 릴스 (Instagram 공식 규격): MP4/MOV, H.264/HEVC, 23~60fps, 가로 1920px 이하, 3초~15분, 300MB 이하
REEL_MIN_SEC, REEL_MAX_SEC = 3, 15 * 60
REEL_MAX_BYTES = 300 * 1024 * 1024
GIT_MAX_BYTES = 95 * 1024 * 1024        # GitHub는 100MB 넘는 파일을 받지 않음

# CLAUDE.md 수리 콘텐츠 규칙: 사실 확인 전 쓰지 않는 표현.
# 확인된 표현은 post.toml의 confirmed_terms에 넣어야 통과합니다.
CHECK_TERMS = ["정품", "정식 부품", "공인", "Apple 공식", "애플 공식", "공식 서비스",
               "최저가", "가장 저렴", "제일 저렴", "100%", "무조건"]
PRICE_RE = re.compile(r"\d[\d,]*\s*(원|만원|만 원)")


def check_image(path, errors, warnings):
    try:
        from PIL import Image
    except ImportError:
        warnings.append("Pillow가 없어 이미지 크기 검사를 건너뜀")
        return None
    if path.stat().st_size > IMAGE_MAX_BYTES:
        errors.append(f"{path.name}: 8MB 초과")
    with Image.open(path) as im:
        if im.format != "JPEG":
            errors.append(f"{path.name}: JPEG가 아님 ({im.format}). 인스타 API는 JPEG만 받음")
        w, h = im.size
    ratio = w / h
    if not (RATIO_MIN - 0.01 <= ratio <= RATIO_MAX + 0.01):
        errors.append(f"{path.name}: 비율 {w}x{h}는 허용 범위(4:5 ~ 1.91:1) 밖")
    if w > 1440:
        warnings.append(f"{path.name}: 너비 {w}px - 인스타가 1440px로 줄임")
    return round(ratio, 3)


def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def moov_before_mdat(path):
    """MP4의 moov(재생 정보)가 영상 데이터보다 앞에 있는지 (Instagram 요구사항)."""
    with open(path, "rb") as f:
        while True:
            head = f.read(8)
            if len(head) < 8:
                return False
            size = int.from_bytes(head[:4], "big")
            kind = head[4:8]
            if kind == b"moov":
                return True
            if kind == b"mdat":
                return False
            if size == 1:
                size = int.from_bytes(f.read(8), "big")
                f.seek(size - 16, 1)
            elif size < 8:
                return False
            else:
                f.seek(size - 8, 1)


def check_video(path, errors, warnings):
    size = path.stat().st_size
    if path.suffix.lower() not in (".mp4", ".mov"):
        errors.append(f"{path.name}: MP4 또는 MOV만 가능")
    if size > REEL_MAX_BYTES:
        errors.append(f"{path.name}: 300MB 초과")
    if size > GIT_MAX_BYTES:
        errors.append(f"{path.name}: 95MB 초과 - GitHub에 올릴 수 없음")
    if not moov_before_mdat(path):
        errors.append(f"{path.name}: 빠른 시작(faststart) 형식이 아님 - make_reel.py로 다시 만드세요")

    exe = ffmpeg_exe()
    if not exe:
        warnings.append("ffmpeg가 없어 영상 길이·코덱 검사를 건너뜀")
        return
    info = subprocess.run([exe, "-hide_banner", "-i", str(path)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    if m:
        sec = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
        if not (REEL_MIN_SEC <= sec <= REEL_MAX_SEC):
            errors.append(f"{path.name}: 길이 {sec:.1f}초 - 3초~15분만 가능")
    v = re.search(r"Video: (\w+).*?, (\d{2,5})x(\d{2,5}).*?([\d.]+) fps", info)
    if not v:
        errors.append(f"{path.name}: 영상 정보를 읽지 못함")
        return
    codec, w, h, fps = v[1], int(v[2]), int(v[3]), float(v[4])
    if codec not in ("h264", "hevc"):
        errors.append(f"{path.name}: 코덱 {codec} - H.264 또는 HEVC만 가능")
    if w > 1920:
        errors.append(f"{path.name}: 가로 {w}px - 최대 1920px")
    if not (23 <= fps <= 60):
        errors.append(f"{path.name}: {fps}fps - 23~60fps만 가능")
    if abs(w / h - 9 / 16) > 0.02:
        warnings.append(f"{path.name}: {w}x{h}는 9:16이 아님 - 위아래나 양옆이 잘리거나 빈 공간이 생길 수 있음")
    a = re.search(r"Audio: (\w+), (\d+) Hz", info)
    if a and (a[1] != "aac" or int(a[2]) > 48000):
        errors.append(f"{path.name}: 오디오 {a[1]} {a[2]}Hz - AAC 48kHz 이하만 가능")


def validate_post(post: Post):
    errors, warnings = [], []
    m = post.meta

    if not ID_RE.match(post.id):
        errors.append("폴더 이름은 영어 소문자·숫자·하이픈만 사용 (이미지 주소에 쓰임)")
    if not post.title:
        warnings.append("title(제목)이 비어 있음")
    if post.type not in SUPPORTED_TYPES:
        errors.append(f"type은 {SUPPORTED_TYPES} 중 하나 (영상은 아직 미연결)")

    try:
        when = post.scheduled_at
    except ValueError:
        errors.append(f"scheduled_at 형식 오류: '{post.scheduled_text}' "
                      "(예: \"2026-11-10 19:00\", 한국 시간)")
        when = None
    if post.approved and when is None and not any("scheduled_at" in e for e in errors):
        errors.append("승인(approved = true)하려면 scheduled_at(예약 시간)이 필요")

    if m.get("kind") == "case":
        if m.get("consent_confirmed") is not True:
            errors.append("실제 수리 사례: 고객 동의 확인(consent_confirmed = true) 필요")
        if m.get("privacy_masked") is not True:
            errors.append("실제 수리 사례: 개인정보 가림 확인(privacy_masked = true) 필요")

    media = post.media
    if not media:
        errors.append("media(이미지 목록)가 비어 있음")
    if post.type == "image" and len(media) != 1:
        errors.append("type = \"image\"는 이미지 1장")
    if post.type == "carousel" and not (CAROUSEL_MIN <= len(media) <= CAROUSEL_MAX):
        errors.append(f"carousel은 이미지 {CAROUSEL_MIN}~{CAROUSEL_MAX}장")
    if post.type == "reel":
        if len(media) != 1:
            errors.append("type = \"reel\"은 영상 파일 1개")
        elif not media[0].exists():
            errors.append(f"영상 없음: {media[0].name}")
        else:
            check_video(media[0], errors, warnings)
        cover = m.get("cover")
        if cover:
            cp = post.folder / cover
            if not cp.exists():
                errors.append(f"표지 이미지 없음: {cover}")
            else:
                with_ratio_errors = []
                check_image(cp, with_ratio_errors, warnings)
                # 표지는 9:16이라 피드 비율 오류는 무시하고 형식·용량만 확인
                errors.extend(e for e in with_ratio_errors if "비율" not in e)
    else:
        ratios = set()
        for p in media:
            if not p.exists():
                errors.append(f"이미지 없음: {p.name}")
                continue
            r = check_image(p, errors, warnings)
            if r:
                ratios.add(r)
        if len(ratios) > 1:
            warnings.append("이미지 비율이 서로 다름 - 첫 장 비율로 잘림")

    # 정보형 릴스 출처 기록 검사 (make_stock_reel.py가 만드는 credits.json)
    credits_path = post.folder / "credits.json"
    if credits_path.exists():
        import json
        info = json.loads(credits_path.read_text(encoding="utf-8"))
        facts = info.get("facts", [])
        if not facts:
            errors.append("credits.json: 사실 확인 출처(facts)가 없음")
        for f in facts:
            if not f.get("url") or not f.get("checked"):
                errors.append(f"출처 URL·확인 날짜 누락: {f.get('claim', '')[:30]}")
            if f.get("source_type") not in ("공식", "언론"):
                errors.append(f"확인되지 않은 출처 유형({f.get('source_type')})은 제작 제외: "
                              f"{f.get('claim', '')[:30]}")
        for s in info.get("stock", []):
            if not all(s.get(k) for k in ("page_url", "author", "license_url", "terms_checked")):
                errors.append(f"스톡 영상 권리 기록 누락: {s.get('id')}")
        if not info.get("selection"):
            warnings.append("주제 선정 근거(selection)가 없음")

    if not post.caption_path.exists():
        errors.append(f"캡션 파일 없음: {post.caption_path.name}")
    else:
        cap = post.caption
        if not cap:
            errors.append("캡션이 비어 있음")
        if len(cap) > CAPTION_MAX:
            errors.append(f"캡션 {len(cap)}자 - 최대 {CAPTION_MAX}자")
        tags = re.findall(r"#\S+", cap)
        if len(tags) > HASHTAG_MAX:
            errors.append(f"해시태그 {len(tags)}개 - 최대 {HASHTAG_MAX}개")
        confirmed = set(m.get("confirmed_terms", []))
        for term in CHECK_TERMS:
            if term in cap and term not in confirmed:
                errors.append(f"확인 필요 표현 '{term}' - 사실이면 confirmed_terms에 추가")
        if PRICE_RE.search(cap) and "가격" not in confirmed:
            errors.append("캡션에 금액 표시 - 확인된 가격이면 confirmed_terms에 \"가격\" 추가")

    return errors, warnings


def main(ids):
    posts = load_posts()
    if ids:
        posts = [p for p in posts if p.id in ids]
    if not posts:
        print("검사할 게시물이 없습니다.")
        return 0
    failed = 0
    for post in posts:
        errors, warnings = validate_post(post)
        mark = "오류" if errors else "통과"
        print(f"[{mark}] {post.id} - {post.title}")
        for e in errors:
            print(f"   ✗ {e}")
        for w in warnings:
            print(f"   ! {w}")
        failed += bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
