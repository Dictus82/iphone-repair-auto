"""Instagram 장기 토큰 갱신 (GitHub Actions에서 매주 실행).

장기 토큰은 60일 동안 유효하고, 갱신하면 다시 60일이 됩니다.
(발급 후 24시간이 지나야 갱신 가능, 60일 안에 갱신하지 않으면 만료되어 다시 발급해야 함)

새 토큰은 화면에 출력하지 않고 지정한 파일에만 씁니다.
워크플로가 이 파일로 GitHub Secret을 바꾼 뒤 바로 지웁니다.

사용법: python automation/refresh_token.py <새 토큰을 쓸 파일>
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def main():
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    if not token:
        sys.exit("IG_ACCESS_TOKEN이 없습니다 (GitHub Secrets 설정 필요)")
    out_file = sys.argv[1]

    query = urllib.parse.urlencode({"grant_type": "ig_refresh_token", "access_token": token})
    try:
        with urllib.request.urlopen(
                f"https://graph.instagram.com/refresh_access_token?{query}", timeout=60) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        sys.exit(f"토큰 갱신 실패 (HTTP {e.code}) {msg}\n"
                 "만료되었다면 안내서의 '토큰 다시 발급' 단계를 진행하세요.")

    new_token = data["access_token"]
    days = int(data.get("expires_in", 0)) // 86400
    print(f"토큰 갱신 완료. 남은 기간 약 {days}일")
    print("::add-mask::" + new_token)  # 혹시 출력돼도 로그에서 가려지게
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(new_token)
    print("토큰 값이 바뀌었습니다." if new_token != token else "토큰 값은 같습니다.")


if __name__ == "__main__":
    main()
