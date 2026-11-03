"""무료 스톡 영상 검색·다운로드·권리 기록 (Pexels / Pixabay 공식 API만 사용).

- 웹사이트 자동 수집(스크래핑)은 약관상 금지이므로 하지 않습니다. 반드시 공식 API를 씁니다.
- 원본 영상은 stock/ 폴더에만 저장합니다 (공개 저장소에 올라가지 않음).
- 영상마다 원본 URL, 제작자, 라이선스 URL, 확인 날짜를 stock/library.json에 기록합니다.
- 내려받은 영상은 review = "pending" 상태이며, 로고·상표·식별 가능한 얼굴 등을 확인해
  "ok"로 바꾼 영상만 릴스 제작에 쓸 수 있습니다.

API 키: Windows 사용자 환경 변수 PEXELS_API_KEY / PIXABAY_API_KEY (사용자가 직접 등록).
키는 화면·파일에 출력하지 않습니다.

사용법
  python automation/stock_library.py search "phone charging" [--source pexels] [--count 3]
  python automation/stock_library.py frames <영상ID>          # 검수용 장면 3장 → outputs/test/
  python automation/stock_library.py review <영상ID> ok|reject "메모"
  python automation/stock_library.py list
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from common import ROOT, fmt_kst, now_kst

STOCK_DIR = ROOT / "stock"
LIBRARY = STOCK_DIR / "library.json"
CACHE_DIR = STOCK_DIR / ".cache"
TEST_DIR = ROOT / "outputs" / "test"
UA = "iphone-repair-reels/1.0 (+https://github.com/Dictus82/iphone-repair-auto)"

SOURCES = {
    "pexels": {
        "key_env": "PEXELS_API_KEY",
        "license_url": "https://www.pexels.com/license/",
        "terms_url": "https://www.pexels.com/terms-of-service/",
        "credit": "Pexels",
    },
    "pixabay": {
        "key_env": "PIXABAY_API_KEY",
        "license_url": "https://pixabay.com/service/license-summary/",
        "terms_url": "https://pixabay.com/service/terms/",
        "credit": "Pixabay",
    },
}
# 이용 조건을 마지막으로 확인한 날짜 (약관이 바뀌면 다시 확인 후 갱신)
TERMS_CHECKED = "2026-11-03"


def api_key(source):
    name = SOURCES[source]["key_env"]
    key = os.environ.get(name, "")
    if not key and sys.platform == "win32":
        import winreg  # 새로 등록한 사용자 환경 변수는 레지스트리에서 바로 읽음
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = winreg.QueryValueEx(k, name)[0]
        except OSError:
            key = ""
    if not key:
        sys.exit(f"{name}가 없습니다. docs/stock-reels.md의 'API 키 발급' 단계를 진행하세요.")
    return key.strip()


def load_library():
    if LIBRARY.exists():
        return json.loads(LIBRARY.read_text(encoding="utf-8"))
    return {}


def save_library(lib):
    STOCK_DIR.mkdir(exist_ok=True)
    LIBRARY.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_json(url, headers, cache_hours=24):
    """API 응답은 24시간 캐시 (Pixabay 요구사항, 같은 검색 반복 호출 방지)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest()[:20] + ".json")
    if cache.exists() and time.time() - cache.stat().st_mtime < cache_hours * 3600:
        return json.loads(cache.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": UA, **headers})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def search_pexels(query, count, orientation):
    key = api_key("pexels")
    params = {"query": query, "orientation": orientation, "size": "medium", "per_page": 15}
    # 키는 URL이 아닌 헤더로만 보내므로 캐시 파일 이름에 키가 들어가지 않음
    data = get_json("https://api.pexels.com/v1/videos/search?" + urllib.parse.urlencode(params),
                    {"Authorization": key})
    out = []
    for v in data.get("videos", []):
        files = [f for f in v.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")]
        # 세로 1080 이하 중 가장 큰 파일 (용량 절약)
        files = [f for f in files if min(f["width"], f["height"]) <= 1080] or files
        if not files:
            continue
        best = max(files, key=lambda f: f["width"] * f["height"])
        out.append({
            "id": f"pexels-{v['id']}", "source": "pexels",
            "page_url": v["url"], "author": v["user"]["name"], "author_url": v["user"]["url"],
            "duration": v.get("duration"), "width": best["width"], "height": best["height"],
            "download_url": best["link"],
        })
        if len(out) >= count:
            break
    return out


def search_pixabay(query, count, orientation):
    key = api_key("pixabay")
    params = {"key": key, "q": query[:100], "video_type": "film", "safesearch": "true",
              "per_page": 20}
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode(params)
    data = get_json(url, {})
    out = []
    for v in data.get("hits", []):
        vids = v.get("videos", {})
        best = vids.get("medium") or vids.get("small")
        if not best or not best.get("url"):
            continue
        out.append({
            "id": f"pixabay-{v['id']}", "source": "pixabay",
            "page_url": v["pageURL"], "author": v["user"],
            "author_url": f"https://pixabay.com/users/{v['user']}-{v['user_id']}/",
            "duration": v.get("duration"), "width": best["width"], "height": best["height"],
            "download_url": best["url"],
        })
        if len(out) >= count:
            break
    return out


def cmd_search(args):
    finder = search_pexels if args.source == "pexels" else search_pixabay
    results = finder(args.query, args.count, args.orientation)
    lib = load_library()
    src = SOURCES[args.source]
    for r in results:
        if r["id"] in lib:
            print(f"- 이미 있음: {r['id']}")
            continue
        dest = STOCK_DIR / args.source / f"{r['id']}.mp4"
        download(r.pop("download_url"), dest)
        lib[r["id"]] = {
            **r,
            "query": args.query,
            "credit": src["credit"],
            "license_url": src["license_url"],
            "terms_url": src["terms_url"],
            "terms_checked": TERMS_CHECKED,
            "downloaded_at_kst": fmt_kst(now_kst()),
            "file": dest.relative_to(ROOT).as_posix(),
            "review": "pending",
            "review_note": "",
        }
        print(f"- 저장: {r['id']} {r['width']}x{r['height']} {r['duration']}초 / {r['author']} / {r['page_url']}")
        time.sleep(1)  # 서버 부담 줄이기
    save_library(lib)


def cmd_frames(args):
    from make_reel import ffmpeg_exe
    lib = load_library()
    item = lib.get(args.id) or sys.exit(f"없는 영상 ID: {args.id}")
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    dur = float(item.get("duration") or 6)
    for i, t in enumerate([0.5, dur / 2, max(dur - 1, 0.6)], 1):
        out = TEST_DIR / f"review_{args.id}_{i}.jpg"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
                        "-i", str(ROOT / item["file"]), "-frames:v", "1",
                        "-vf", "scale=360:-2", str(out)], check=True)
        print(out)


def cmd_review(args):
    lib = load_library()
    if args.id not in lib:
        sys.exit(f"없는 영상 ID: {args.id}")
    lib[args.id]["review"] = args.result
    lib[args.id]["review_note"] = args.note
    lib[args.id]["reviewed_at_kst"] = fmt_kst(now_kst())
    save_library(lib)
    print(f"{args.id}: {args.result} {args.note}")


def cmd_list(_):
    for k, v in load_library().items():
        print(f"{k:16} {v['review']:8} {v['width']}x{v['height']} {v.get('duration')}초 "
              f"{v['author']} | {v['page_url']} | {v['review_note']}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--source", choices=list(SOURCES), default="pexels")
    s.add_argument("--count", type=int, default=3)
    s.add_argument("--orientation", default="portrait")
    s.set_defaults(func=cmd_search)
    f = sub.add_parser("frames")
    f.add_argument("id")
    f.set_defaults(func=cmd_frames)
    r = sub.add_parser("review")
    r.add_argument("id")
    r.add_argument("result", choices=["ok", "reject"])
    r.add_argument("note", nargs="?", default="")
    r.set_defaults(func=cmd_review)
    sub.add_parser("list").set_defaults(func=cmd_list)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
