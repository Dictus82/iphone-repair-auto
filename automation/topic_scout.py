"""아이폰 뉴스·정보 수집 → 릴스 주제 후보 순위표 (PC에서 실행, 결과는 outputs/topics/에 저장).

수집 출처
- 공식(키 불필요): Apple 뉴스룸(한국), Apple 보안 업데이트 목록, Apple 개발자 릴리스
- 언론(선택): 네이버 뉴스 검색 API  - NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 필요
- 검색 관심도(선택): 네이버 데이터랩 검색어 트렌드 API (같은 키) - 상대값(0~100)만 제공

원칙
- 보도 날짜(언론 발행일)와 사건 날짜(공식 발표·출시일)를 따로 기록
- 출처 유형: 공식 / 언론 / 사용자 제보 보도 / 루머·전망  → 제보·루머는 기본 제작 제외
- 검색 관심도를 확인하지 못하면 "미확인"으로 표시 (인기·검색량을 추정하지 않음)
- 기사 문장은 저장·사용하지 않음. 제목과 링크만 후보 확인용으로 기록 (대본은 사실 확인 후 자체 작성)

사용법: python automation/topic_scout.py [--days 14]
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from common import KST, POSTS_DIR, ROOT, load_posts, now_kst

OUT_DIR = ROOT / "outputs" / "topics"
HISTORY = OUT_DIR / "history.json"
UA = "Mozilla/5.0 (iphone-repair-topic-scout)"

CATEGORIES = {
    "신제품": {"words": ["신형", "출시", "사전예약", "가격", "공개"], "impact": 3},
    "iOS": {"words": ["iOS", "업데이트", "새 기능", "지원 기종", "베타"], "impact": 3},
    "보안·서비스": {"words": ["보안", "취약점", "서비스 프로그램", "리콜", "교환 프로그램"], "impact": 3},
    "문제": {"words": ["배터리", "발열", "충전", "통신", "카메라", "버그", "오류", "먹통"], "impact": 2},
    "중고·개인정보·팁": {"words": ["중고", "개인정보", "사용법", "꿀팁", "설정", "활성화 잠금"], "impact": 1},
    "비교·구매": {"words": ["비교", "구매", "자급제", "요금제", "할인", "보상"], "impact": 2},
}
NEWS_QUERIES = ["아이폰 출시", "아이폰 가격", "iOS 업데이트", "아이폰 보안 업데이트",
                "아이폰 배터리", "아이폰 발열", "아이폰 충전", "아이폰 통신 오류",
                "아이폰 카메라", "애플 서비스 프로그램", "중고 아이폰", "아이폰 개인정보"]
RUMOR_WORDS = ["루머", "유출", "전망", "예상", "관측", "가능성", "소문", "카더라", "것으로 알려",
               "점쳐", "썰", "렌더링", "목업"]
REPORT_WORDS = ["사용자들", "커뮤니티", "제보", "호소", "불만", "레딧", "Reddit", "누리꾼", "일부 사용자"]


def fetch(url, headers=None, data=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})}, data=data)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def strip(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


IPHONE_WORDS = ["아이폰", "iPhone", "iOS", "Siri", "Apple Intelligence", "AppleCare", "애플케어",
                "앱스토어", "App Store", "iCloud", "Apple 계정", "Apple ID"]
OFF_TOPIC = ["실적", "MacBook", "iMac", "Mac ", "iPad", "Watch", "Vision Pro", "Apple TV", "macOS"]


def categorize(text):
    head = text.split("(")[0]   # 괄호 안 기종 목록(iPhone 11 등)은 분류에서 제외
    if not any(w.lower() in head.lower() for w in IPHONE_WORDS) or \
            any(w in head for w in OFF_TOPIC) and "iPhone" not in head and "iOS" not in head:
        return ["아이폰 무관"]
    cats = [c for c, v in CATEGORIES.items() if any(w.lower() in head.lower() for w in v["words"])]
    return cats or ["기타"]


# ---------- 공식 출처 ----------
def apple_newsroom():
    t = fetch("https://www.apple.com/kr/newsroom/rss-feed.rss")
    items = []
    for e in re.findall(r"<entry>(.*?)</entry>", t, re.S):
        title = strip(re.sub(r"<!\[CDATA\[|\]\]>", "", re.search(r"<title>(.*?)</title>", e, re.S)[1]))
        link = re.search(r'<link href="([^"]+)"/>', e)[1]
        updated = re.search(r"<updated><!\[CDATA\[(.*?)\]\]>", e)[1]
        dt = datetime.fromisoformat(updated.replace("Z", "+00:00")).astimezone(KST)
        items.append({"title": title, "url": link, "source": "Apple 뉴스룸(한국)",
                      "source_type": "공식", "event_date": dt.date().isoformat(),
                      "report_date": dt.date().isoformat()})
    return items


def apple_security():
    t = fetch("https://support.apple.com/en-us/100100")
    items = []
    for row in re.findall(r"<tr>(.*?)</tr>", t, re.S)[1:40]:
        cells = [" ".join(strip(c).split()) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 3 or "iOS" not in cells[0]:
            continue
        try:
            d = datetime.strptime(cells[2], "%d %b %Y").date().isoformat()
        except ValueError:
            continue
        name = cells[0].replace("This update has no published CVE entries.", "").strip()
        items.append({"title": f"보안 업데이트: {name} (대상: {cells[1][:60]})",
                      "url": "https://support.apple.com/en-us/100100",
                      "source": "Apple 보안 업데이트", "source_type": "공식",
                      "event_date": d, "report_date": d})
    return items


def apple_developer():
    t = fetch("https://developer.apple.com/news/releases/rss/releases.rss")
    items = []
    for it in re.findall(r"<item>(.*?)</item>", t, re.S):
        title = strip(re.search(r"<title>(.*?)</title>", it, re.S)[1])
        if not title.startswith("iOS"):
            continue
        d = parsedate_to_datetime(re.search(r"<pubDate>(.*?)</pubDate>", it)[1]).astimezone(KST)
        link = strip(re.search(r"<link>(.*?)</link>", it, re.S)[1])
        beta = "beta" in title.lower() or "RC" in title
        items.append({"title": f"{'베타·RC: ' if beta else '정식 배포: '}{title}", "url": link,
                      "source": "Apple 개발자 릴리스", "source_type": "공식",
                      "event_date": d.date().isoformat(), "report_date": d.date().isoformat(),
                      "note": "베타는 일반 사용자 대상 아님" if beta else ""})
    return items


# ---------- 네이버 (선택) ----------
def naver_keys():
    ids = {}
    for name in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"):
        v = os.environ.get(name, "")
        if not v and sys.platform == "win32":
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                    v = winreg.QueryValueEx(k, name)[0]
            except OSError:
                v = ""
        ids[name] = v.strip()
    if not all(ids.values()):
        return None
    return {"X-Naver-Client-Id": ids["NAVER_CLIENT_ID"],
            "X-Naver-Client-Secret": ids["NAVER_CLIENT_SECRET"]}


def naver_news(headers):
    items = []
    for q in NEWS_QUERIES:
        url = "https://openapi.naver.com/v1/search/news.json?" + urllib.parse.urlencode(
            {"query": q, "display": 20, "sort": "date"})
        data = json.loads(fetch(url, headers))
        for it in data.get("items", []):
            title = strip(it["title"])
            desc = strip(it.get("description", ""))
            text = f"{title} {desc}"
            if any(w in text for w in RUMOR_WORDS):
                stype = "루머·전망"
            elif any(w in text for w in REPORT_WORDS):
                stype = "사용자 제보 보도"
            else:
                stype = "언론"
            link = it.get("originallink") or it["link"]
            if "apple.com" in link:
                stype = "공식"
            d = parsedate_to_datetime(it["pubDate"]).astimezone(KST).date().isoformat()
            items.append({"title": title, "url": link, "source": "네이버 뉴스 검색",
                          "source_type": stype, "report_date": d,
                          "event_date": "기사 확인 필요", "query": q})
    return items


def naver_interest(headers, keywords):
    """최근 7일 평균 / 이전 21일 평균 (상대값). 절대 검색량이 아님."""
    end = now_kst().date()
    start = end - timedelta(days=27)
    result = {}
    for i in range(0, len(keywords), 5):
        groups = [{"groupName": k, "keywords": [k]} for k in keywords[i:i + 5]]
        body = json.dumps({"startDate": start.isoformat(), "endDate": end.isoformat(),
                           "timeUnit": "date", "keywordGroups": groups}).encode()
        data = json.loads(fetch("https://openapi.naver.com/v1/datalab/search",
                                {**headers, "Content-Type": "application/json"}, body))
        for r in data.get("results", []):
            vals = [p["ratio"] for p in r["data"]]
            if len(vals) >= 14:
                recent, before = sum(vals[-7:]) / 7, sum(vals[:-7]) / max(len(vals) - 7, 1)
                result[r["title"]] = {"recent7": round(recent, 1), "before21": round(before, 1),
                                      "trend": round(recent / before, 2) if before else None}
    return result


# ---------- 선정 ----------
def existing_titles():
    titles = [p.title for p in load_posts()]
    if HISTORY.exists():
        titles += json.loads(HISTORY.read_text(encoding="utf-8"))
    return titles


def overlap(a, b):
    ta, tb = set(re.findall(r"[가-힣A-Za-z0-9.]{2,}", a)), set(re.findall(r"[가-힣A-Za-z0-9.]{2,}", b))
    return len(ta & tb) / max(min(len(ta), len(tb)), 1)


def score(item, today, titles, interest):
    reasons, s = [], 0
    if item["source_type"] in ("루머·전망", "사용자 제보 보도"):
        return None, [f"제외: {item['source_type']} (확인되지 않은 내용은 기본 제외)"]
    if item.get("note", "").startswith("베타"):
        return None, ["제외: 베타 (일반 사용자 대상 아님)"]
    if item["categories"] == ["아이폰 무관"]:
        return None, ["제외: 아이폰 사용자와 관련성 낮음 (실적·Mac·iPad 등)"]
    try:
        days = (today - datetime.fromisoformat(item["report_date"]).date()).days
    except ValueError:
        days = 99
    fresh = 3 if days <= 3 else 2 if days <= 7 else 1 if days <= 30 else 0
    s += fresh
    reasons.append(f"최신성 {fresh}점 (보도 {days}일 전)")
    impact = max(CATEGORIES.get(c, {"impact": 1})["impact"] for c in item["categories"])
    s += impact
    reasons.append(f"소비자 영향 {impact}점 ({', '.join(item['categories'])})")
    src = 3 if item["source_type"] == "공식" else 2
    s += src
    reasons.append(f"출처 신뢰 {src}점 ({item['source_type']})")
    dup = max((overlap(item["title"], t) for t in titles), default=0)
    if dup >= 0.6:
        s -= 3
        reasons.append("기존 콘텐츠와 중복 -3점")
    hit = [v for k, v in interest.items() if k in item["title"]]
    if hit and hit[0]["trend"]:
        bonus = 2 if hit[0]["trend"] >= 1.3 else 1 if hit[0]["trend"] >= 1.0 else 0
        s += bonus
        reasons.append(f"검색 관심도 {bonus}점 (네이버 상대값 최근7일/이전21일 = {hit[0]['trend']})")
    else:
        reasons.append("검색 관심도 미확인")
    return s, reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    today = now_kst().date()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    items, notes = [], []
    for name, fn in [("Apple 뉴스룸", apple_newsroom), ("Apple 보안 업데이트", apple_security),
                     ("Apple 개발자 릴리스", apple_developer)]:
        try:
            got = fn()
            items += got
            notes.append(f"{name}: {len(got)}건")
        except Exception as e:
            notes.append(f"{name}: 수집 실패 ({type(e).__name__})")

    headers = naver_keys()
    interest = {}
    if headers:
        try:
            got = naver_news(headers)
            items += got
            notes.append(f"네이버 뉴스: {len(got)}건")
            interest = naver_interest(headers, NEWS_QUERIES)
            notes.append(f"네이버 데이터랩 관심도: {len(interest)}개 키워드")
        except Exception as e:
            notes.append(f"네이버: 수집 실패 ({type(e).__name__})")
    else:
        notes.append("네이버 뉴스·검색 관심도: 키 없음 → 미수집 (관심도 '미확인')")

    cutoff = today - timedelta(days=args.days)
    seen, ranked, excluded = set(), [], []
    titles = existing_titles()
    for it in items:
        try:
            if datetime.fromisoformat(it["report_date"]).date() < cutoff:
                continue
        except ValueError:
            pass
        key = re.sub(r"\W", "", re.sub(r"\([0-9A-Z]+\)", "", it["title"]))[:40]  # 빌드 번호만 다른 항목 합침
        if key in seen:
            continue
        seen.add(key)
        it["categories"] = categorize(it["title"])
        s, reasons = score(it, today, titles, interest)
        it["reasons"] = reasons
        (excluded if s is None else ranked).append({**it, "score": s})
    ranked.sort(key=lambda x: (x["score"], x["report_date"]), reverse=True)

    stamp = today.isoformat()
    report = {"collected_at": now_kst().isoformat(timespec="minutes"), "notes": notes,
              "candidates": ranked, "excluded": excluded, "interest": interest}
    (OUT_DIR / f"{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    md = [f"# 주제 후보 ({stamp}, 최근 {args.days}일)", "", "수집: " + " / ".join(notes), "",
          "| 순위 | 점수 | 출처 유형 | 보도일 | 사건일 | 분류 | 제목 |", "|---|---|---|---|---|---|---|"]
    for i, c in enumerate(ranked[:15], 1):
        md.append(f"| {i} | {c['score']} | {c['source_type']} | {c['report_date']} | "
                  f"{c['event_date']} | {', '.join(c['categories'])} | [{c['title']}]({c['url']}) |")
    md += ["", "## 선정 근거 (상위 5개)"]
    for c in ranked[:5]:
        md.append(f"- **{c['title']}**: " + "; ".join(c["reasons"]))
    md += ["", f"## 제외 ({len(excluded)}건)"]
    for c in excluded[:15]:
        md.append(f"- {c['source_type']} | {c['report_date']} | {c['title']} → {c['reasons'][0]}")
    md += ["", "※ 한국 출시·가격·적용 여부는 후보 선정 후 apple.com/kr 등 공식 자료로 별도 확인합니다."]
    (OUT_DIR / f"{stamp}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:24]))
    print(f"\n저장: {OUT_DIR / (stamp + '.md')}")


if __name__ == "__main__":
    main()
