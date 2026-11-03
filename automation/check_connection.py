"""연결 확인 (읽기 전용 - 게시하지 않음). GitHub Actions '연결 확인'에서 실행합니다.

- 토큰이 작동하는지
- 토큰에 연결된 인스타그램 계정 ID와 아이디(username)
- 게시 권한이 있는지 (24시간 게시 한도 조회)
토큰 값은 출력하지 않습니다. 계정 ID는 비밀 정보가 아닙니다.
"""
import sys

from publish import ApiError, Instagram


def main():
    ig = Instagram(require_user=False)
    print(f"로그인 방식: {ig.login} / 주소: {ig.base}")
    ok = True

    try:
        if ig.login == "unified":
            data = ig.call("GET", "me/assigned_instagram_accounts").get("data", [])
            print(f"토큰에 연결된 인스타그램 계정 {len(data)}개:")
            for acc in data:
                acc_id = acc.get("id", "")
                name = acc.get("username", "")
                if acc_id and not name:
                    try:
                        name = ig.call("GET", acc_id, fields="username").get("username", "")
                    except ApiError:
                        name = "(아이디 조회 실패)"
                print(f"  - 계정 ID: {acc_id}  아이디: @{name}")
        else:
            me = ig.call("GET", "me", fields="user_id,username")
            print(f"  - 계정 ID: {me.get('user_id')}  아이디: @{me.get('username')}")
    except ApiError as e:
        print(f"계정 조회 실패: {e}")
        ok = False

    if ig.user:
        try:
            info = ig.call("GET", ig.user, fields="username")
            print(f"IG_USER_ID 계정: @{info.get('username')}")
            limit = ig.call("GET", f"{ig.user}/content_publishing_limit",
                            fields="quota_usage,config")
            print(f"게시 권한 확인됨. 최근 24시간 API 게시 수: {limit}")
        except ApiError as e:
            print(f"IG_USER_ID 확인 실패: {e}")
            ok = False
    else:
        print("IG_USER_ID가 아직 없습니다. 위 계정 ID를 Variables에 등록하세요.")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
