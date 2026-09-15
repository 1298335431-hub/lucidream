"""Read-only release check. Never load local .env or print config values/secrets."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from app.core.config import PROJECT_ROOT, Settings


def release_checks(settings, oauth, environ):
    origins = settings.parsed_cors_origins()
    def https_origin(value):
        url = urlsplit(value)
        return (url.scheme == "https" and bool(url.hostname) and url.hostname != "localhost"
                and not url.username and not url.password and not url.query and not url.fragment
                and url.path in ("", "/"))

    callback = oauth.get("redirectUri") or ""
    callback_url = urlsplit(callback)
    callback_origin = f"{callback_url.scheme}://{callback_url.netloc}"
    identity = oauth.get("identityPath")
    return [
        ("正式环境及强制登录", settings.environment == "production" and settings.auth_enabled),
        ("生图总额度为 8 次", settings.image_quota_total == 8),
        ("真实模型及凭证已注入", settings.model_mode == "aliyun" and bool(settings.dashscope_api_key)),
        ("HTTPS 同源入口", bool(origins) and all(https_origin(origin) for origin in origins)),
        ("数据库使用显式绝对路径", settings.database_path.is_absolute()
         and settings.database_path.resolve() != (PROJECT_ROOT / "data/dreamcard.db").resolve()),
        ("知识索引存在", settings.knowledge_index_path.is_file()),
        ("前端构建存在", (PROJECT_ROOT / "dist/index.html").is_file()),
        ("知乎回调配置并匹配入口", callback_origin in origins and https_origin(callback_origin)
         and callback_url.path == "/auth/callback" and not callback_url.query and not callback_url.fragment),
        ("知乎稳定身份字段已配置（仍需平台实测确认）", isinstance(identity, list) and bool(identity)),
        ("知乎凭证通过环境注入", bool(environ.get("ZHIHU_OAUTH_APP_KEY")) and bool(environ.get("ZHIHU_ACCESS_SECRET"))),
        # Deliberately not satisfiable with a self-certified environment flag.
        # Replace these blockers only after implementation and real acceptance evidence.
        ("云端数据持久化与异地恢复验收（尚未接入）", False),
        ("图片对象存储与私有访问验收（尚未接入）", False),
        ("真实知乎授权、账号隔离及云端完整流程验收（待部署测试版）", False),
    ]


def main():
    try:
        settings = Settings(_env_file=None)
        config = json.loads((PROJECT_ROOT / "integrations/zhihu-login/hackathon.config.json").read_text())
        checks = release_checks(settings, config.get("oauth", {}), os.environ)
    except Exception:
        print("检查失败：配置缺失或无效（配置值已隐藏）")
        return 1
    for name, ok in checks:
        print(f"{'通过' if ok else '待完成'} · {name}")
    passed = all(ok for _, ok in checks)
    print("具备发布条件" if passed else "尚不具备正式开放条件；本检查不部署、不创建云资源")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
