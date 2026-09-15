"""Print aggregate-only local shadow retrieval metrics."""

from __future__ import annotations

import json

from app.core.config import Settings
from app.storage.repository import DreamRepository


def main() -> None:
    settings = Settings()
    repository = DreamRepository(settings.database_path)
    print(
        json.dumps(
            repository.summarize_original_knowledge_shadow(),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
