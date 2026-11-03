"""게시물 검사. 승인 전 확인용이며, 자동 게시 직전에도 다시 검사합니다.

사용법: python automation/validate.py [게시물ID ...]
오류가 있으면 종료 코드 1.
"""
import re
import sys

from common import ID_RE, Post, load_posts

# Instagram 공식 게시 API 기준 (2026-11 확인)
CAPTION_MAX = 2200
HASHTAG_MAX = 30
CAROUSEL_MIN, CAROUSEL_MAX = 2, 20
IMAGE_MAX_BYTES = 8 * 1024 * 1024
RATIO_MIN, RATIO_MAX = 4 / 5, 1.91      # 세로 4:5 ~ 가로 1.91:1
SUPPORTED_TYPES = ("image", "carousel")  # 영상(reel)은 별도 연결 단계에서 추가

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
