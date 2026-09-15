"""Evaluate local-only retrieval for original Simplified Chinese cards."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.original_knowledge import LocalOriginalKnowledgeRetriever


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CARDS_PATH = (
    PROJECT_ROOT / "data" / "knowledge" / "自建知识库" / "processed" / "cards.jsonl"
)
CASES_PATH = (
    PROJECT_ROOT
    / "data"
    / "knowledge"
    / "自建知识库"
    / "evaluation"
    / "local-retrieval-cases.json"
)
REPORT_PATH = CASES_PATH.with_name("local-retrieval-report.json")


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    retriever = LocalOriginalKnowledgeRetriever.from_jsonl(CARDS_PATH)
    results: list[dict] = []
    passed = 0
    for case in cases:
        result = retriever.retrieve(case["query"], limit=5)
        actual = [hit.card.card_id for hit in result.hits]
        expected = case["expected"]
        # `expected` is the reviewed set of plausible cards for a compound
        # query.  The production selector intentionally returns one primary
        # and at most two strong supporting cards, so it must not be judged by
        # the old "return every plausible card" contract.  A passing result
        # therefore needs a non-empty primary from the reviewed set and may
        # only retain reviewed supporting cards.  Fallback fixtures still
        # require an exact empty result.
        if case["fallback"]:
            expected_found = actual == []
        else:
            expected_found = bool(actual) and actual[0] in expected and set(actual).issubset(expected)
        fallback_matches = result.fallback is case["fallback"]
        case_passed = expected_found and fallback_matches
        passed += int(case_passed)
        results.append(
            {
                **case,
                "actual": actual,
                "matched_terms": {
                    hit.card.card_id: list(hit.matched_terms) for hit in result.hits
                },
                "passed": case_passed,
            }
        )
    report = {
        "case_count": len(cases),
        "passed": passed,
        "pass_rate": passed / len(cases) if cases else 0,
        "model_calls": 0,
        "results": results,
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: report[key] for key in report if key != "results"}, ensure_ascii=False))
    if passed != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
