"""Download the two reviewed Project Gutenberg text candidates.

The source text and its licence notice are preserved unchanged. Existing files
are verified and never overwritten. This script does not clean, ingest, embed,
or send any content to a model.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx


ROOT = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "解梦素材"
SOURCES = (
    {
        "source_id": "freud-interpretation-of-dreams-en",
        "title": "The Interpretation of Dreams",
        "author": "Sigmund Freud",
        "translator": "A. A. Brill",
        "ebook_number": 66048,
        "url": "https://www.gutenberg.org/cache/epub/66048/pg66048.txt",
        "catalogue_url": "https://www.gutenberg.org/ebooks/66048",
    },
    {
        "source_id": "miller-ten-thousand-dreams-en",
        "title": "Ten Thousand Dreams Interpreted; Or, What's in a Dream",
        "author": "Gustavus Hindman Miller",
        "translator": None,
        "ebook_number": 926,
        "url": "https://www.gutenberg.org/cache/epub/926/pg926.txt",
        "catalogue_url": "https://www.gutenberg.org/ebooks/926",
    },
)
MAX_BYTES = 12 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    headers = {"User-Agent": "DreamCardSourceReview/0.1 (local research)"}
    with httpx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
        for source in SOURCES:
            parsed = urlsplit(source["url"])
            if parsed.scheme != "https" or parsed.hostname != "www.gutenberg.org":
                raise ValueError("Unexpected source host")
            folder = ROOT / source["source_id"]
            folder.mkdir(exist_ok=True)
            target = folder / "source.txt"
            if not target.exists():
                partial = folder / f"source-{stamp}.partial"
                size = 0
                with client.stream("GET", source["url"]) as response:
                    response.raise_for_status()
                    with partial.open("xb") as output:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > MAX_BYTES:
                                raise ValueError("Text download exceeds safety limit")
                            output.write(chunk)
                raw = partial.read_bytes()
                text = raw.decode("utf-8")
                expected = f"Project Gutenberg eBook of {source['title']}"
                if expected.casefold() not in text[:1000].casefold():
                    raise ValueError("Downloaded text does not match catalogue title")
                if "PROJECT GUTENBERG EBOOK" not in text or len(text) < 10_000:
                    raise ValueError("Downloaded text is incomplete")
                partial.rename(target)
            else:
                target.read_text(encoding="utf-8")
            manifest = {
                "source_id": source["source_id"],
                "title": source["title"],
                "author": source["author"],
                "translator": source["translator"],
                "ebook_number": source["ebook_number"],
                "retrieved_at": stamp,
                "file": "source.txt",
                "bytes": target.stat().st_size,
                "sha256": sha256_file(target),
                "source_url": source["url"],
                "catalogue_url": source["catalogue_url"],
                "format": "UTF-8 plain text",
                "status": "candidate_not_ingested",
                "commercial_approval": False,
                "cleaning_status": "not_started",
                "notes": (
                    "The catalogue marks this edition public domain in the USA. "
                    "That is not worldwide commercial clearance; review the target "
                    "jurisdiction, edition, translator, Gutenberg licence, and trademark terms."
                ),
            }
            manifest_path = folder / f"manifest-{stamp}.json"
            with manifest_path.open("x", encoding="utf-8") as output:
                json.dump(manifest, output, ensure_ascii=False, indent=2)
            print(
                f"Verified {source['source_id']}: {target.stat().st_size} bytes, "
                f"sha256={manifest['sha256']}",
                flush=True,
            )


if __name__ == "__main__":
    main()
