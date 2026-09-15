"""Compile original dream-card Markdown drafts into deterministic JSONL."""

from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = PROJECT_ROOT / "data" / "knowledge" / "自建知识库" / "样稿"
OUTPUT_DIR = PROJECT_ROOT / "data" / "knowledge" / "自建知识库" / "processed"
OUTPUT_PATH = OUTPUT_DIR / "cards.jsonl"
REPORT_PATH = OUTPUT_DIR / "report.json"

SECTION_MAP = {
    "适用边界": "scope_note",
    "梦卡原创解读": "original_interpretation",
    "文化背景": "cultural_context",
    "可以问问自己": "reflection_prompts",
    "温和建议": "gentle_actions",
    "安全提示": "safety_note",
    "依据": "evidence_notes",
}


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ValueError("frontmatter_missing")
    _, raw, body = text.split("---\n", 2)
    data: dict[str, object] = {}
    current_list: str | None = None
    for line in raw.splitlines():
        if line.startswith("  - "):
            if current_list is None:
                raise ValueError("frontmatter_list_without_key")
            values = data.setdefault(current_list, [])
            assert isinstance(values, list)
            values.append(line[4:].strip())
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            data[key] = value
            current_list = None
        else:
            data[key] = []
            current_list = key
    return data, body


def parse_sections(body: str) -> dict[str, object]:
    sections: dict[str, object] = {}
    matches = list(re.finditer(r"^## (.+)$", body, flags=re.MULTILINE))
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        output_key = SECTION_MAP.get(name)
        if output_key is None:
            continue
        if name in {"可以问问自己", "温和建议", "依据"}:
            sections[output_key] = [
                line[2:].strip() for line in content.splitlines() if line.startswith("- ")
            ]
        else:
            sections[output_key] = re.sub(r"\n{2,}", "\n\n", content)
    return sections


def compile_card(path: Path) -> dict:
    frontmatter, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    record = {**frontmatter, **parse_sections(body)}
    required = {
        "card_id",
        "title",
        "aliases",
        "retrieval_terms",
        "category",
        "rights_status",
        "status",
        "author",
        "reviewer",
        "version",
        "created_at",
        "updated_at",
        "scope_note",
        "original_interpretation",
        "cultural_context",
        "reflection_prompts",
        "gentle_actions",
        "safety_note",
        "evidence_notes",
    }
    missing = sorted(required - record.keys())
    if missing:
        raise ValueError(f"card_fields_missing:{path.name}:{','.join(missing)}")
    empty = sorted(key for key in required if not record[key])
    if empty:
        raise ValueError(f"card_fields_empty:{path.name}:{','.join(empty)}")
    record["source_file"] = str(path.relative_to(PROJECT_ROOT))
    record["retrieval_enabled"] = False
    record["production_eligible"] = False
    return record


def main() -> None:
    paths = sorted(SOURCE_DIR.glob("DREAM-*.md"))
    records = [compile_card(path) for path in paths]
    ids = [record["card_id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_card_id")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    report = {
        "card_count": len(records),
        "card_ids": ids,
        "retrieval_enabled_count": sum(
            bool(record["retrieval_enabled"]) for record in records
        ),
        "production_eligible_count": sum(
            bool(record["production_eligible"]) for record in records
        ),
        "model_calls": 0,
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
