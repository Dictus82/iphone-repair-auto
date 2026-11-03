"""완성된 이미지·캡션으로 게시물 초안 폴더를 만듭니다 (승인 전 상태).

사용법:
  python automation/new_post.py <게시물ID> --title "제목" --images <이미지폴더> [--caption caption.txt]
  - 이미지 폴더 안의 PNG/JPG를 이름 순서대로 01.jpg, 02.jpg ... (JPEG)로 변환
  - 캡션을 지정하지 않으면 이미지 폴더의 caption.txt 사용
  - approved = false, scheduled_at = "" 로 만듭니다. 승인과 예약은 사장님이 정합니다.
"""
import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image

from common import ID_RE, POSTS_DIR

TEMPLATE = '''# 게시물 정보 - 사람이 수정하는 파일입니다.
title = "{title}"

# image(1장) 또는 carousel(2~20장). 영상(reel)은 별도 연결 단계에서 추가합니다.
type = "{type}"

# info = 정보형, case = 실제 수리 사례 (case는 아래 두 확인 항목이 true여야 게시됨)
kind = "{kind}"
# consent_confirmed = true   # 고객 동의 받음
# privacy_masked = true      # 잠금화면·전화번호·IMEI·얼굴·이름 가림

# 한국 시간. 예: "2026-11-10 19:00"
scheduled_at = ""

# 사장님이 이미지와 캡션을 확인한 뒤에만 true로 바꿉니다.
approved = false

media = [{media}]
caption_file = "caption.txt"

# 사실로 확인된 표현만 넣습니다. 예: ["정품"]
confirmed_terms = []
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("post_id")
    ap.add_argument("--title", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--caption")
    ap.add_argument("--kind", default="info", choices=["info", "case"])
    args = ap.parse_args()

    if not ID_RE.match(args.post_id):
        sys.exit("게시물 ID는 영어 소문자·숫자·하이픈만 사용 (예: 2026-11-screen-info)")
    dest = POSTS_DIR / args.post_id
    if dest.exists():
        sys.exit(f"이미 있는 게시물입니다: {dest}")

    src = Path(args.images)
    images = sorted(p for p in src.iterdir()
                    if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    if not images:
        sys.exit(f"이미지가 없습니다: {src}")
    caption = Path(args.caption) if args.caption else src / "caption.txt"
    if not caption.exists():
        sys.exit(f"캡션 파일이 없습니다: {caption}")

    dest.mkdir(parents=True)
    names = []
    for i, img_path in enumerate(images, 1):
        name = f"{i:02d}.jpg"
        with Image.open(img_path) as im:
            im.convert("RGB").save(dest / name, "JPEG", quality=92, optimize=True)
        names.append(name)
    shutil.copyfile(caption, dest / "caption.txt")

    (dest / "post.toml").write_text(TEMPLATE.format(
        title=args.title.replace('"', "'"),
        type="image" if len(names) == 1 else "carousel",
        kind=args.kind,
        media=", ".join(f'"{n}"' for n in names),
    ), encoding="utf-8")
    print(f"초안 생성: {dest} ({len(names)}장, 미승인)")


if __name__ == "__main__":
    main()
