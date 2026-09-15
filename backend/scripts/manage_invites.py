"""Local operator CLI. Never expose as a public HTTP endpoint."""
import argparse
from app.core.config import Settings
from app.services.invite_auth import InviteAuth
from app.storage.repository import DreamRepository


def main():
    parser = argparse.ArgumentParser(description="管理内测邀请码")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--issue", type=int, metavar="COUNT")
    group.add_argument("--disable", metavar="ACCOUNT_ID")
    group.add_argument("--list", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    DreamRepository(settings.database_path)
    auth = InviteAuth(settings.database_path)
    if args.issue is not None:
        if not 1 <= args.issue <= 100:
            parser.error("一次只能签发 1–100 个")
        for _ in range(args.issue):
            account, code = auth.issue()
            print(f"账户 {account}\n邀请码 {code}\n（仅展示一次，请单独发给一位用户）")
    elif args.disable:
        with auth.connect() as db:
            changed = db.execute("UPDATE invite_accounts SET enabled=0 WHERE id=?", (args.disable,)).rowcount
            db.execute("DELETE FROM auth_sessions WHERE account_id=?", (args.disable,))
        print("账户已停用，登录已失效，梦境数据保留" if changed else "没有找到该账户")
    else:
        with auth.connect() as db:
            for row in db.execute("SELECT id, enabled, created_at FROM invite_accounts ORDER BY created_at"):
                print(dict(row))


if __name__ == "__main__":
    main()
