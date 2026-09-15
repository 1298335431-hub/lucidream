"""Paid end-to-end evaluation with synthetic dreams and a temporary database.

The script is deliberately development-only: it uses the candidate local index,
never the production database, and persists only synthetic test inputs/results.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.storage.repository import DreamRepository


CASES = (
    ("森林与鹿", "我梦见月光下的森林，一只鹿安静地站在树间，我感到平静。"),
    ("从高处坠落", "我梦见自己从很高的地方坠落，心里很害怕。"),
    ("在水中行走", "我梦见自己在清澈的水中慢慢行走，周围很安静。"),
    ("回到旧房子", "我梦见回到小时候住过的旧房子，房间里的东西还和以前一样。"),
    ("被陌生人追赶", "我梦见在一条陌生的街道上被一个陌生人追赶，我一直奔跑并感到害怕。"),
    ("在天空飞行", "我梦见自己轻轻飞到城市上空，看见下面的灯光，觉得自由又有些紧张。"),
    ("遇见蛇", "我梦见一条蛇从草丛里缓慢爬过，我站在远处不敢靠近。"),
    ("牙齿松动", "我梦见自己的牙齿变得松动，照镜子时感到不安。"),
    ("回到考场", "我梦见又回到学校考试，试卷还没有写完，周围很安静。"),
    ("错过火车", "我梦见赶到车站时火车刚刚开走，只能站在站台上等待。"),
    ("雨中迷路", "我梦见下着细雨，在陌生城市的街道里找不到回家的路。"),
    ("海边涨潮", "我梦见站在海边，潮水一点点靠近脚边，天空是灰蓝色的。"),
    ("山路行走", "我梦见沿着一条陡峭的山路向上走，背着很重的包。"),
    ("镜中自己", "我梦见站在镜子前，镜子里的自己没有说话，只是看着我。"),
    ("旧友来访", "我梦见多年不见的朋友来到家里，我们坐着聊天，感觉很亲切。"),
    ("猫在窗边", "我梦见一只黑白相间的猫坐在窗边看着外面的月亮。"),
    ("屋内起火", "我梦见厨房里冒出火光，我马上跑出去叫人帮忙，心里很着急。"),
    ("婴儿哭泣", "我梦见抱着一个哭泣的婴儿，怎么安慰都不太确定。"),
    ("门打不开", "我梦见站在一扇紧闭的门前，反复推门却怎么也打不开。"),
    ("在花园散步", "我梦见在开满白花的花园里散步，闻到淡淡的香味，心情放松。"),
)

MAX_SECONDS = 60
# Heuristic only. The actual generation contract remains the primary safeguard.
PROHIBITED_CERTAINTY = ("必然", "注定", "一定会发生", "寿命", "确诊", "治疗方案")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("work/rag-20case-evaluation.json"),
        help="Local JSON report path. The report contains synthetic cases only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings()
    if settings.model_mode != "aliyun":
        raise SystemExit("DREAMCARD_MODEL_MODE must be aliyun")
    reports = []
    with TemporaryDirectory(prefix="dreamcard-interpretation-eval-") as directory:
        database_path = Path(directory) / "evaluation.db"
        client = TestClient(create_app(
            settings=settings,
            database_path=database_path,
        ))
        repository = DreamRepository(database_path)
        for label, dream_text in CASES:
            started = time.perf_counter()
            extracted = client.post("/api/v1/dreams/extract", json={"dream_text": dream_text})
            if extracted.status_code != 200:
                reports.append({"case": label, "stage": "extract", "status": extracted.status_code,
                                "error": extracted.json().get("error", {}).get("code")})
                continue
            session = extracted.json()
            answer = "记不清" if session.get("clarification") else None
            confirmed = client.put(f"/api/v1/dreams/{session['id']}/symbols", json={
                "symbols": session["symbols"], "clarification_answer": answer,
            })
            if confirmed.status_code != 200 or confirmed.json()["status"] != "ready_to_generate":
                reports.append({"case": label, "stage": "confirm", "status": confirmed.status_code})
                continue
            generated = client.post(f"/api/v1/dreams/{session['id']}/interpretation")
            elapsed = round(time.perf_counter() - started, 3)
            if generated.status_code != 200:
                record = repository.get_generation(session["id"], confirmed.json()["revision"])
                reports.append({
                    "case": label, "stage": "interpretation", "status": generated.status_code,
                    "error": generated.json().get("error", {}).get("code"),
                    "error_detail": record.get("error_code") if record else None,
                    "elapsed_seconds": elapsed,
                })
                continue
            payload = generated.json()
            restored = client.get(f"/api/v1/dreams/{session['id']}/interpretation")
            interpretation = payload["interpretation"]
            rendered_text = json.dumps(interpretation, ensure_ascii=False)
            certainty_hits = [term for term in PROHIBITED_CERTAINTY if term in rendered_text]
            reading_count = len(interpretation["readings"])
            source_count = len(payload["sources"])
            acceptance_checks = {
                "within_60_seconds": elapsed <= MAX_SECONDS,
                "has_cited_reading": reading_count >= 1,
                "has_traceable_source": source_count >= 1,
                "restored_identically": restored.status_code == 200 and restored.json() == payload,
                "no_prohibited_certainty_phrase": not certainty_hits,
                "production_still_blocked": payload["production_eligible"] is False,
            }
            reports.append({
                "case": label, "stage": "complete", "status": 200,
                "elapsed_seconds": elapsed, "title": interpretation["title"],
                "reading_count": reading_count,
                "source_count": source_count,
                "source_chapters": [source["chapter"] for source in payload["sources"]],
                "review_status": payload["review_status"],
                "production_eligible": payload["production_eligible"],
                "certainty_hits": certainty_hits,
                "acceptance_checks": acceptance_checks,
                "passed_automated_checks": all(acceptance_checks.values()),
            })
            print(json.dumps(reports[-1], ensure_ascii=False), flush=True)
    completed = [report for report in reports if report["stage"] == "complete"]
    passed = [report for report in completed if report["passed_automated_checks"]]
    summary = {
        "case_count": len(CASES),
        "completed_count": len(completed),
        "automated_pass_count": len(passed),
        "first_pass_rate": round(len(passed) / len(CASES), 4),
        "latency_seconds": {
            "max": max((report["elapsed_seconds"] for report in completed), default=None),
            "average": round(
                sum(report["elapsed_seconds"] for report in completed) / len(completed), 3
            ) if completed else None,
        },
        "production_whitelist_changed": False,
        "moderation_mode": settings.moderation_mode,
        "note": "Automated checks do not replace manual quality, legal, or content-safety review.",
    }
    result = {"summary": summary, "reports": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "output": str(args.output)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
