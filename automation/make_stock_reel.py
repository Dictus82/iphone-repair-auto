"""스톡 영상 배경 + AI 나레이션 + 음성에 맞춘 자막 + 매장 안내로 세로 릴스(1080x1920)를 만들고,
미승인 게시물 초안으로 등록합니다. PC(Claude Code)에서 실행합니다.

- 배경: stock_library.py로 받은 영상 중 review = "ok"인 것만 사용 (원본은 저장소에 올리지 않음)
- 나레이션: 문장마다 음성을 따로 만들고 실제 길이를 재서 자막 표시 시간을 맞춤
- 화면 상단에 "이해를 돕기 위한 참고 영상" 표시 (스톡 영상을 실제 매장 작업으로 소개하지 않음)
- 음악 없음 (사용 권한이 확인된 음악 파일을 spec에 넣을 때만 추가하도록 확장 예정)

사용법: python automation/make_stock_reel.py <spec.toml> [--test-background] [--out <mp4>]
  --test-background : 스톡 영상 대신 테스트용 움직이는 배경 (게시물로 등록하지 않음, outputs/test/에 저장)

spec.toml 예시는 docs/stock-reels.md 참고.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import wave
from pathlib import Path

from PIL import Image, ImageDraw

from common import ID_RE, POSTS_DIR, ROOT, fmt_kst, now_kst
from make_reel import POST_TEMPLATE, ffmpeg_exe, load_font, wrap
from stock_library import load_library

W, H, FPS = 1080, 1920, 30
NAVY = "#14284B"
LEAD, GAP, TAIL = 0.3, 0.25, 0.9   # 시작 여백, 문장 사이, 끝 여백(초)
SAMPLE_RATE = 48000


# ---------- 음성 ----------
def tts_sapi(lines, voice, rate, out_dir):
    """Windows 내장 음성(SAPI)으로 문장별 WAV 생성. 무료, 인터넷 불필요."""
    data = out_dir / "lines.json"
    data.write_text(json.dumps({"voice": voice, "rate": rate, "lines": lines,
                                "dir": str(out_dir)}, ensure_ascii=False), encoding="utf-8")
    ps = out_dir / "tts.ps1"
    ps.write_text(r'''
$cfg = Get-Content -Raw -Encoding UTF8 $args[0] | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$i = 0
foreach ($line in $cfg.lines) {
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice($cfg.voice)
  $s.Rate = [int]$cfg.rate
  $s.SetOutputToWaveFile((Join-Path $cfg.dir ("line{0:D2}.wav" -f $i)), $fmt)
  $s.Speak($line)
  $s.Dispose()
  $i++
}
''', encoding="utf-8-sig")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(ps), str(data)], check=True)
    return [out_dir / f"line{i:02d}.wav" for i in range(len(lines))]


def trim_silence(path, threshold=300):
    """문장 앞뒤의 무음을 잘라 자막과 음성이 더 정확히 맞도록 함."""
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        frames = w.readframes(w.getnframes())
    width = params.sampwidth
    samples = [int.from_bytes(frames[i:i + width], "little", signed=True)
               for i in range(0, len(frames), width)]
    loud = [i for i, s in enumerate(samples) if abs(s) > threshold]
    if not loud:
        return
    pad = int(0.05 * params.framerate)
    a, b = max(loud[0] - pad, 0), min(loud[-1] + pad, len(samples))
    with wave.open(str(path), "wb") as w:
        w.setparams(params)
        w.writeframes(frames[a * width:b * width])


def wav_seconds(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def build_narration(wavs, gaps, out_path):
    """문장 WAV들을 정해진 간격으로 이어 붙여 하나의 WAV로."""
    with wave.open(str(wavs[0]), "rb") as w:
        params = w.getparams()
    rate, width = params.framerate, params.sampwidth
    silence = lambda sec: b"\x00" * (int(sec * rate) * width)
    with wave.open(str(out_path), "wb") as out:
        out.setparams(params)
        out.writeframes(silence(LEAD))
        for wav_path, gap in zip(wavs, gaps):
            with wave.open(str(wav_path), "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))
            out.writeframes(silence(gap))


# ---------- 그래픽 ----------
def subtitle_png(text, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = load_font(60)
    lines = wrap(d, text, font, W - 220)
    line_h = 82
    box_h = line_h * len(lines) + 56
    top = 1480 - box_h   # 릴스 하단 UI(캡션·버튼)보다 위
    d.rounded_rectangle([70, top, W - 70, top + box_h], radius=28, fill=(0, 0, 0, 170))
    y = top + 26
    for line in lines:
        w = d.textbbox((0, 0), line, font=font)[2]
        d.text(((W - w) // 2, y), line, fill="white", font=font)
        y += line_h
    img.save(path)


def label_png(text, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = load_font(34)
    w = d.textbbox((0, 0), text, font=font)[2]
    x = (W - w) // 2
    d.rounded_rectangle([x - 28, 150, x + w + 28, 214], radius=32, fill=(0, 0, 0, 140))
    d.text((x, 158), text, fill="white", font=font)
    img.save(path)


def end_card_png(lines, path):
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    d.rectangle([110, 520, 200, 530], fill="white")
    y = 600
    for i, line in enumerate(lines):
        font = load_font(96 if i == 0 else 58)
        d.text((110, y), line, fill="white", font=font)
        y += (150 if i == 0 else 92)
    img.save(path)


# ---------- 영상 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--test-background", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    spec_path = Path(args.spec).resolve()
    with open(spec_path, "rb") as f:
        spec = tomllib.load(f)
    lines = spec["lines"]
    end_line = spec["end_line"]
    narration = lines + [end_line]
    post_id = spec["post_id"]
    if not ID_RE.match(post_id):
        sys.exit("post_id는 영어 소문자·숫자·하이픈만 사용")

    # 배경 영상 확인 (검수 통과한 스톡만)
    clips, credits = [], []
    if not args.test_background:
        lib = load_library()
        for cid in spec["clips"]:
            item = lib.get(cid)
            if not item:
                sys.exit(f"스톡 라이브러리에 없는 영상: {cid}")
            if item["review"] != "ok":
                sys.exit(f"검수 통과(ok)하지 않은 영상: {cid} ({item['review']})")
            clips.append(ROOT / item["file"])
            credits.append({k: item[k] for k in ("id", "credit", "author", "author_url",
                                                  "page_url", "license_url", "terms_checked")})

    if args.test_background:
        out_mp4 = Path(args.out) if args.out else ROOT / "outputs" / "test" / f"{post_id}_test.mp4"
        post_dir = None
    else:
        post_dir = POSTS_DIR / post_id
        if post_dir.exists():
            sys.exit(f"이미 있는 게시물입니다: {post_dir}")
        out_mp4 = post_dir / "reel.mp4"
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # 1) 나레이션
        voice = spec.get("voice", "Microsoft Heami Desktop")
        wavs = tts_sapi(narration, voice, spec.get("rate", 1), tmp)
        for w in wavs:
            trim_silence(w)
        durs = [wav_seconds(w) for w in wavs]
        gaps = [GAP] * (len(narration) - 1) + [TAIL]
        build_narration(wavs, gaps, tmp / "narration.wav")

        # 2) 타임라인: 자막 i는 문장 i가 나오는 동안 표시
        times, t = [], LEAD
        for d, g in zip(durs, gaps):
            times.append((t, t + d + (g if g == GAP else 0)))
            t += d + g
        total = t
        stock_end = times[-1][0] - GAP / 2 if len(times) > 1 else 0
        stock_end = max(stock_end, times[-2][1] if len(times) > 1 else 0)
        end_dur = total - stock_end

        # 3) 그래픽
        label_png(spec.get("label", "이해를 돕기 위한 참고 영상"), tmp / "label.png")
        end_card_png(spec["end_card"], tmp / "end.png")
        subs = []
        for i, text in enumerate(spec.get("subtitles", narration)):
            p = tmp / f"sub{i:02d}.png"
            subtitle_png(text, p)
            subs.append(p)

        # 4) 배경 구간: 문장마다 한 장면 (영상이 문장 수보다 적으면 반복 사용)
        seg_bounds = [0.0] + [times[i][0] for i in range(1, len(lines))] + [stock_end]
        segs = [(seg_bounds[i], seg_bounds[i + 1]) for i in range(len(lines))]

        cmd = [ffmpeg_exe(), "-y", "-loglevel", "error"]
        if args.test_background:
            for i, (a, b) in enumerate(segs):
                cmd += ["-f", "lavfi", "-t", f"{b - a:.3f}", "-i",
                        f"gradients=s=1080x1920:r={FPS}:speed=0.02:n=3:seed={i + 1}"]
        else:
            offset = float(spec.get("clip_offset", 0.5))
            for i, (a, b) in enumerate(segs):
                cmd += ["-stream_loop", "-1", "-ss", f"{offset:.2f}", "-t", f"{b - a:.3f}",
                        "-i", str(clips[i % len(clips)])]
        n = len(segs)
        cmd += ["-loop", "1", "-t", f"{end_dur:.3f}", "-i", str(tmp / "end.png")]
        cmd += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(tmp / "label.png")]
        for p in subs:
            cmd += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(p)]
        audio_idx = n + 2 + len(subs)
        cmd += ["-i", str(tmp / "narration.wav")]

        f = []
        for i, (a, b) in enumerate(segs):
            f.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                     f"fps={FPS},setsar=1,format=yuv420p,trim=duration={b - a:.3f},"
                     f"setpts=PTS-STARTPTS[s{i}]")
        f.append(f"[{n}:v]scale={W}:{H},fps={FPS},setsar=1,format=yuv420p,"
                 f"trim=duration={end_dur:.3f},setpts=PTS-STARTPTS[se]")
        f.append("".join(f"[s{i}]" for i in range(n)) + f"[se]concat=n={n + 1}:v=1:a=0[base]")
        f.append(f"[base][{n + 1}:v]overlay=0:0:enable='lt(t,{stock_end:.3f})'[v0]")
        last = "v0"
        for i, (a, b) in enumerate(times):
            f.append(f"[{last}][{n + 2 + i}:v]overlay=0:0:"
                     f"enable='between(t,{a:.3f},{b:.3f})'[v{i + 1}]")
            last = f"v{i + 1}"
        f.append(f"[{last}]fade=t=out:st={total - 0.4:.3f}:d=0.4,format=yuv420p[vout]")
        cmd += ["-filter_complex", ";".join(f), "-map", "[vout]", "-map", f"{audio_idx}:a",
                "-t", f"{total:.3f}",
                "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS),
                "-g", str(FPS), "-keyint_min", str(FPS), "-sc_threshold", "0", "-flags", "+cgop",
                "-crf", "21", "-maxrate", "8M", "-bufsize", "16M",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", str(out_mp4)]
        if post_dir:
            post_dir.mkdir(parents=True)
        try:
            subprocess.run(cmd, check=True)
        except Exception:
            if post_dir:
                shutil.rmtree(post_dir, ignore_errors=True)
            raise

    timeline = [{"start": round(a, 2), "end": round(b, 2), "text": s}
                for (a, b), s in zip(times, spec.get("subtitles", narration))]
    print(f"영상 생성: {out_mp4} ({total:.1f}초)")
    for tl in timeline:
        print(f"  {tl['start']:5.2f}~{tl['end']:5.2f}s  {tl['text']}")

    if not post_dir:
        return

    # 표지: 첫 자막이 보이는 장면
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{times[0][0] + 0.8:.2f}",
                    "-i", str(out_mp4), "-frames:v", "1", "-q:v", "3",
                    str(post_dir / "cover.jpg")], check=True)

    # 캡션 + 영상 출처 표기
    caption = (spec_path.parent / spec.get("caption_file", "caption.txt")).read_text(
        encoding="utf-8-sig").strip()
    if credits:
        names = ", ".join(sorted({f"{c['author']}({c['credit']})" for c in credits}))
        caption += f"\n\n참고 영상: {names}"
    (post_dir / "caption.txt").write_text(caption + "\n", encoding="utf-8")

    # 공개해도 되는 기록만 저장 (원본 영상 파일 경로·키 없음)
    (post_dir / "credits.json").write_text(json.dumps({
        "created_at_kst": fmt_kst(now_kst()),
        "selection": spec.get("selection", {}),
        "stock": credits,
        "facts": spec.get("facts", []),
        "voice": f"Windows SAPI: {voice}",
        "music": "없음",
        "timeline": timeline,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (post_dir / "post.toml").write_text(POST_TEMPLATE.format(
        title=spec.get("title", post_id).replace('"', "'"), kind="info",
        case_lines="# 스톡 참고 영상 + 정보형 나레이션 (실제 매장 작업 아님)\n"),
        encoding="utf-8")
    print(f"미승인 초안 등록: {post_dir}")


if __name__ == "__main__":
    main()
