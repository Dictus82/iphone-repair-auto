"""게시물 현황표 (초안 / 승인 / 예약 시간 / 게시 결과).

사용법: python automation/status.py            # 화면 출력
        python automation/status.py --write    # content/SCHEDULE.md 로 저장
"""
import sys

from common import POSTS_DIR, STATUS_KO, fmt_kst, load_posts, now_kst


def table():
    rows = ["| 게시물 ID | 제목 | 예약(KST) | 승인 | 상태 | 링크 |",
            "|---|---|---|---|---|---|"]
    for p in load_posts():
        r = p.result
        rows.append("| {} | {} | {} | {} | {} | {} |".format(
            p.id, p.title, p.scheduled_text or "-",
            "O" if p.approved else "-",
            STATUS_KO.get(p.status, p.status),
            r.get("permalink", "") or r.get("error", "") or "",
        ))
    return "\n".join(rows)


def main():
    if "--write" in sys.argv:
        # 파일에는 현재 시각을 넣지 않음 (내용이 바뀔 때만 커밋되도록)
        out = POSTS_DIR.parent / "SCHEDULE.md"
        out.write_text(f"# 게시 일정 (한국 시간)\n\n{table()}\n", encoding="utf-8")
        print("저장:", out)
    else:
        print(f"# 게시 일정\n\n기준: {fmt_kst(now_kst())} (한국 시간)\n\n{table()}\n")


if __name__ == "__main__":
    main()
