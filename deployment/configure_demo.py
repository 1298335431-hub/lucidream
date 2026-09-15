"""Explicit one-time secret injection using stdin; no credentials in argv/files."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings
from app.services.invite_auth import new_invite_code


def keychain(service, account):
    result = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", service, "-a", account, "-w"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--initialize-demo-code", action="store_true")
    args = parser.parse_args()
    if not args.origin.startswith("https://") or any(char in args.origin for char in "\n\r\"'"):
        raise SystemExit("HTTPS origin required")
    settings = Settings()
    if not settings.dashscope_api_key:
        raise SystemExit("Local model credential not configured; nothing changed")
    env = {"DREAMCARD_ENV": "production", "DREAMCARD_AUTH_ENABLED": "true",
           "DREAMCARD_MODEL_MODE": "aliyun", "DREAMCARD_CORS_ORIGINS": args.origin.rstrip("/"),
           "DASHSCOPE_API_KEY": settings.dashscope_api_key,
           "DASHSCOPE_API_HOST": settings.dashscope_api_host}
    for field in ("qwen_extract_model", "qwen_interpret_model", "wan_image_model", "embedding_model", "embedding_dimensions", "rerank_model", "moderation_mode", "moderation_region", "moderation_access_key_id", "moderation_access_key_secret", "moderation_security_token"):
        value = getattr(settings, field)
        if value is not None:
            env[Settings.model_fields[field].alias] = value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
    config = json.loads((ROOT / "integrations/zhihu-login/hackathon.config.json").read_text())
    for key, value in {
        "ZHIHU_OAUTH_APP_KEY": keychain(config["oauth"]["credentialService"], config["oauth"]["credentialAccount"]),
        "ZHIHU_ACCESS_SECRET": keychain("zhihu-cli", "access-secret"),
    }.items():
        if value:
            env[key] = value
    demo_code = new_invite_code() if args.initialize_demo_code else None
    if demo_code:
        env["DREAMCARD_DEMO_INVITE_CODE"] = demo_code
    payload = "\n".join(f"{key}={json.dumps(value)}" for key, value in env.items()) + "\n"
    result = subprocess.run(["vefaas", "env", "import", "--appId", args.app_id, "--file", "/dev/stdin", "--yes"], input=payload, capture_output=True, text=True, timeout=60)
    # Deliberately do not echo CLI stdout/stderr, which may include environment values.
    if result.returncode:
        print(json.dumps({"configured": False, "exit_code": result.returncode}))
        raise SystemExit(1)
    print(json.dumps({"configured": True, "keys": list(env), "demo_access_code": demo_code}))


if __name__ == "__main__":
    main()
