"""Local, opt-in live probes with synthetic data only. May incur provider charges."""

import argparse
import json
from typing import Literal

from pydantic import BaseModel

from app.core.config import Settings
from app.schemas.dream import ExtractionResult
from app.services.aliyun import AliyunModels, ModelServiceError


class Probe(BaseModel):
    ok: Literal[True]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--live-text", action="store_true", help="两次真实文字调用 可能计费")
    group.add_argument("--live-image", action="store_true", help="提交一张测试图片 可能计费 不自动重试")
    group.add_argument("--task-id", help="查询之前提交的图片任务 不重新生成")
    args = parser.parse_args()
    settings = Settings()
    models = AliyunModels(settings)
    try:
        if args.live_text:
            models.chat_json(settings.qwen_extract_model,
                             "仅提取梦境事实，不解梦，输出 JSON。",
                             "测试文本：我在森林里看到一只鹿，感到平静。", ExtractionResult)
            print(json.dumps({"extract": "passed", "model": settings.qwen_extract_model}))
            models.chat_json(settings.qwen_interpret_model, "这是接口测试，输出 JSON。",
                             '仅返回 {"ok": true}', Probe)
            print(json.dumps({"interpret_connectivity": "passed", "model": settings.qwen_interpret_model}))
        elif args.live_image:
            task = models.submit_image("接口测试插图：月光下安静的森林与一只银色鹿。电影感暗黑奇幻写实，冷灰蓝体积月光，无文字。")
            print(task.model_dump_json(exclude={"image_urls"}))
        elif args.task_id:
            task = models.get_image_task(args.task_id)
            # Do not print signed asset URLs into terminal histories.
            print(json.dumps({"task_id": task.task_id, "status": task.status,
                              "image_count": len(task.image_urls), "review_status": task.review_status}))
            if task.status in ("FAILED", "CANCELED", "UNKNOWN"):
                return 1
        else:
            print(json.dumps({"mode": settings.model_mode,
                              "api_key_configured": bool(settings.dashscope_api_key),
                              "remote_requests_sent": 0}))
    except ModelServiceError as error:
        print(json.dumps({"error": error.code}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
