"""Read-only configuration by default; --live sends two synthetic paid requests."""
import argparse
import json

from app.core.config import Settings
from app.services.moderation import TextModerator, ModerationError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Send two synthetic texts to the paid moderation service")
    args = parser.parse_args()
    moderator = TextModerator(Settings())
    print(json.dumps(moderator.configuration(), ensure_ascii=False))
    if not args.live:
        return
    try:
        for direction in ("input", "output"):
            result = moderator.check("测试梦境：我在月光下散步。", direction)
            print(json.dumps({"direction": direction, "risk_level": result.risk_level, "allowed": result.allowed}, ensure_ascii=False))
    except ModerationError as error:
        print(json.dumps({"error": error.code}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
