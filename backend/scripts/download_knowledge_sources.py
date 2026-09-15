"""Download only the two reviewed public catalogue candidates; never ingest or OCR.

Run with .venv/bin/python backend/scripts/download_knowledge_sources.py.
Preserves source metadata and hashes. Existing files are verified, never overwritten.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "解梦素材"
SOURCES = {
    "File:Shanghai 夢林玄解三十四卷首一卷.pdf": "menglin-xuanjie-shanghai",
    "File:NLC511-023031404015388-27665 夢占逸旨.pdf": "mengzhan-yizhi-1939",
}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with httpx.Client(timeout=60, headers={"User-Agent": "DreamCardSourceReview/0.1 (local research)"}) as client:
        response = client.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "format": "json", "prop": "imageinfo|revisions",
            "iiprop": "url|size|sha1|extmetadata", "rvprop": "ids|timestamp",
            "titles": "|".join(SOURCES),
        })
        response.raise_for_status()
        pages = response.json()["query"]["pages"].values()
        for page in pages:
            title = page["title"]
            source_id = SOURCES[title]
            info = page["imageinfo"][0]
            if info["extmetadata"].get("LicenseShortName", {}).get("value") != "Public domain":
                raise ValueError("Source licence changed; review manually before downloading")
            url = info["url"]
            if urlsplit(url).scheme != "https" or urlsplit(url).hostname != "upload.wikimedia.org":
                raise ValueError("Unexpected download host")
            folder = ROOT / source_id
            folder.mkdir(exist_ok=True)
            target = folder / "source.pdf"
            if not target.exists():
                partial = folder / f"source-{stamp}.partial"
                size = 0
                with client.stream("GET", url) as download:
                    download.raise_for_status()
                    with partial.open("xb") as output:
                        for chunk in download.iter_bytes():
                            size += len(chunk)
                            if size > info["size"]:
                                raise ValueError("Download exceeds catalogue size")
                            output.write(chunk)
                target_to_check = partial
            else:
                target_to_check = target
            sha1, sha256 = hashlib.sha1(), hashlib.sha256()
            with target_to_check.open("rb") as source:
                if source.read(5) != b"%PDF-":
                    raise ValueError("Not a PDF")
                source.seek(0)
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    sha1.update(chunk)
                    sha256.update(chunk)
            if target_to_check.stat().st_size != info["size"] or sha1.hexdigest() != info["sha1"]:
                raise ValueError("Checksum mismatch; keep partial file for inspection")
            if target_to_check != target:
                target_to_check.rename(target)
            manifest = {
                "source_id": source_id, "retrieved_at": stamp,
                "file": "source.pdf", "bytes": info["size"], "sha256": sha256.hexdigest(),
                "page_count_catalogue": info.get("pagecount"),
                "status": "candidate_not_ingested", "commercial_approval": False,
                "ocr_status": "not_started", "completeness": "not_page_by_page_verified",
                "catalogue_snapshot": page,
                "notes": "PD label is the source's claim, not a legal clearance. Review edition, modern introductions, attribution, scan quality and missing pages before ingestion.",
            }
            manifest_path = folder / f"manifest-{stamp}.json"
            with manifest_path.open("x", encoding="utf-8") as output:
                json.dump(manifest, output, ensure_ascii=False, indent=2)
            print(f"Verified {source_id}: {info['size']} bytes, {info.get('pagecount')} catalogue pages", flush=True)


if __name__ == "__main__":
    main()
