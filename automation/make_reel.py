"""사진 + 짧은 문구로 세로 릴스 영상(1080x1920)을 만들고, 미승인 게시물 초안으로 등록합니다.

PC(Claude Code)에서 실행합니다. 무료 도구만 사용: Pillow + imageio-ffmpeg(ffmpeg 내장).
실제 수리 사례 영상은 사장님이 제공한, 개인정보를 가린 사진만 사용합니다.

사용법:
  python automation/make_reel.py <게시물ID> --spec <reel.toml> [--caption caption.txt]

reel.toml 예시 (이미지 경로는 reel.toml 위치 기준):
  title = "배터리 교체 안내 릴스"
  kind = "info"              # info(정보형) / case(실제 수리 사례)
  fit = "contain"            # contain: 이미지 전체를 배경 위에 / cover: 화면 가득(가운데 기준으로 잘림)
  background = "#14284B"     # contain일 때 배경색
  seconds = 3.0              # 장면별 기본 길이(초)

  [[slides]]
  image = "01.jpg"
  text = "수리 전"           # 선택. 화면 아래쪽에 크게 표시 (20자 이내 권장)
  seconds = 2.5              # 선택. 이 장면만 길이 변경
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import ID_RE, POSTS_DIR

W, H = 1080, 1920
FPS = 30
FADE = 0.35
FONT_CANDIDATES = ["C:/Windows/Fonts/malgunbd.ttf",
                   "/usr/share/fonts/truetype/noto/NotoSansKR-Bold.ttf",
                   "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]

POST_TEMPLATE = '''# 게시물 정보 - 사람이 수정하는 파일입니다.
title = "{title}"

# reel = 세로 영상(릴스). 영상은 make_reel.py로 만듭니다.
type = "reel"

# info = 정보형, case = 실제 수리 사례 (case는 아래 두 확인 항목이 true여야 게시됨)
kind = "{kind}"
{case_lines}
# 한국 시간. 예: "2026-11-10 19:00"
scheduled_at = ""

# 사장님이 영상과 캡션을 확인한 뒤에만 true로 바꿉니다.
approved = false

media = ["reel.mp4"]
cover = "cover.jpg"          # 릴스 탭 표지 (9:16 JPEG)
share_to_feed = true         # true: 피드와 릴스 탭 모두 / false: 릴스 탭만
caption_file = "caption.txt"

# 사실로 확인된 표현만 넣습니다. 예: ["정품"]
confirmed_terms = []
'''


def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg가 없습니다 (imageio-ffmpeg 필요)")


def load_font(size):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    sys.exit("한글 글꼴을 찾지 못했습니다")


def wrap(draw, text, font, max_w):
    lines = []
    for para in text.replace("\\n", "\n").split("\n"):
        cur = ""
        for word in para.split(" "):
            test = f"{cur} {word}".strip()
            if draw.textbbox((0, 0), test, font=font)[2] <= max_w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def render_slide(img_path, text, fit, bg):
    canvas = Image.new("RGB", (W, H), bg)
    with Image.open(img_path) as im:
        im = im.convert("RGB")
        if fit == "cover":
            scale = max(W / im.width, H / im.height)
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
            left, top = (im.width - W) // 2, (im.height - H) // 2
            canvas.paste(im.crop((left, top, left + W, top + H)))
        else:
            scale = min(W / im.width, H / im.height)
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
            canvas.paste(im, ((W - im.width) // 2, (H - im.height) // 2))

    if text:
        draw = ImageDraw.Draw(canvas, "RGBA")
        font = load_font(76)
        lines = wrap(draw, text, font, W - 200)
        line_h = 100
        box_h = line_h * len(lines) + 80
        # 릴스 화면 아래쪽 UI(캡션·버튼)를 피해 하단에서 약간 위에 배치
        top = H - 420 - box_h
        draw.rounded_rectangle([60, top, W - 60, top + box_h], radius=32, fill=(0, 0, 0, 150))
        y = top + 40
        for line in lines:
            w = draw.textbbox((0, 0), line, font=font)[2]
            draw.text(((W - w) // 2, y), line, fill="white", font=font)
            y += line_h
    return canvas


def build_video(frames, durations, out_path):
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error"]
    for f, d in zip(frames, durations):
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", str(f)]
    total = sum(durations)
    cmd += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=48000:cl=stereo"]
    parts = []
    for i, d in enumerate(durations):
        parts.append(f"[{i}:v]fade=t=in:st=0:d={FADE},fade=t=out:st={d - FADE:.2f}:d={FADE},"
                      f"setsar=1,format=yuv420p[v{i}]")
    concat = "".join(f"[v{i}]" for i in range(len(durations)))
    parts.append(f"{concat}concat=n={len(durations)}:v=1:a=0[v]")
    cmd += ["-filter_complex", ";".join(parts),
            "-map", "[v]", "-map", f"{len(durations)}:a",
            # Instagram 릴스 규격: H.264, 4:2:0, closed GOP, moov 앞쪽, AAC 48kHz 스테레오
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-g", str(FPS), "-keyint_min", str(FPS), "-sc_threshold", "0",
            "-flags", "+cgop", "-crf", "21", "-maxrate", "8M", "-bufsize", "16M",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", "-shortest", str(out_path)]
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("post_id")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--caption")
    args = ap.parse_args()

    if not ID_RE.match(args.post_id):
        sys.exit("게시물 ID는 영어 소문자·숫자·하이픈만 사용")
    dest = POSTS_DIR / args.post_id
    if dest.exists():
        sys.exit(f"이미 있는 게시물입니다: {dest}")

    spec_path = Path(args.spec).resolve()
    with open(spec_path, "rb") as f:
        spec = tomllib.load(f)
    slides = spec.get("slides", [])
    if not slides:
        sys.exit("reel.toml에 [[slides]]가 없습니다")
    base = spec_path.parent
    fit = spec.get("fit", "cover")
    bg = spec.get("background", "#000000")
    default_sec = float(spec.get("seconds", 3.0))
    kind = spec.get("kind", "info")

    caption = Path(args.caption) if args.caption else base / "caption.txt"
    if not caption.exists():
        sys.exit(f"캡션 파일이 없습니다: {caption}")
    for s in slides:
        if not (base / s["image"]).exists():
            sys.exit(f"이미지가 없습니다: {base / s['image']}")
        if len(s.get("text", "")) > 30:
            print(f"참고: 문구가 깁니다 ({s['text']}) - 20자 이내 권장")

    durations = [float(s.get("seconds", default_sec)) for s in slides]
    if sum(durations) < 3:
        sys.exit("릴스는 최소 3초")

    dest.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            frames = []
            for i, s in enumerate(slides):
                frame = render_slide(base / s["image"], s.get("text", ""), fit, bg)
                p = Path(tmp) / f"slide{i:02d}.png"
                frame.save(p)
                frames.append(p)
                if i == 0:
                    frame.save(dest / "cover.jpg", "JPEG", quality=92)
            build_video(frames, durations, dest / "reel.mp4")
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise

    shutil.copyfile(caption, dest / "caption.txt")
    case_lines = ("consent_confirmed = false   # 고객 동의 받았으면 true\n"
                  "privacy_masked = false      # 개인정보 가렸으면 true\n") if kind == "case" else \
                 "# consent_confirmed = true   # 고객 동의 받음\n# privacy_masked = true      # 개인정보 가림\n"
    (dest / "post.toml").write_text(POST_TEMPLATE.format(
        title=spec.get("title", args.post_id).replace('"', "'"), kind=kind,
        case_lines=case_lines), encoding="utf-8")
    size_mb = (dest / "reel.mp4").stat().st_size / 1024 / 1024
    print(f"릴스 초안 생성: {dest} ({len(slides)}장면, {sum(durations):.1f}초, {size_mb:.1f}MB, 미승인)")


if __name__ == "__main__":
    main()
