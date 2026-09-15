"""Prepare traceable RAG candidates from the two local Gutenberg texts.

This is a deterministic, offline transformation. It never calls a model,
translates text, embeds chunks, or changes the downloaded source files.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MATERIAL_ROOT = PROJECT_ROOT / "data" / "knowledge" / "解梦素材"
MAX_CHARS = 2_600
RIGHTS_STATUS = "candidate_not_commercially_approved"


@dataclass(frozen=True)
class Paragraph:
    text: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    paragraphs: tuple[Paragraph, ...]


SOURCES = (
    {
        "source_id": "freud-interpretation-of-dreams-en",
        "book": "The Interpretation of Dreams",
        "author": "Sigmund Freud",
        "translator": "A. A. Brill",
        "source_url": "https://www.gutenberg.org/ebooks/66048",
        "kind": "freud_chapters",
    },
    {
        "source_id": "miller-ten-thousand-dreams-en",
        "book": "Ten Thousand Dreams Interpreted; Or, What's in a Dream",
        "author": "Gustavus Hindman Miller",
        "translator": None,
        "source_url": "https://www.gutenberg.org/ebooks/926",
        "kind": "miller_entries",
    },
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_body(raw_text: str) -> tuple[list[str], int]:
    lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    start = next(
        index for index, line in enumerate(lines)
        if line.strip().startswith("*** START OF THE PROJECT GUTENBERG EBOOK")
    )
    end = next(
        index for index, line in enumerate(lines[start + 1 :], start + 1)
        if line.strip().startswith("*** END OF THE PROJECT GUTENBERG EBOOK")
    )
    if end <= start + 1:
        raise ValueError("Gutenberg body markers are invalid")
    # Offset is one-based and points at the first retained source line.
    return lines[start + 1 : end], start + 2


def paragraphs_from_lines(lines: list[str], line_offset: int) -> tuple[Paragraph, ...]:
    paragraphs: list[Paragraph] = []
    buffer: list[str] = []
    paragraph_start = 0
    for index, line in enumerate(lines):
        if line.strip():
            if not buffer:
                paragraph_start = index
            buffer.append(line.rstrip())
            continue
        if buffer:
            text = re.sub(r"\s+", " ", "\n".join(buffer)).strip()
            paragraphs.append(Paragraph(
                text=text,
                line_start=line_offset + paragraph_start,
                line_end=line_offset + index - 1,
            ))
            buffer = []
    if buffer:
        paragraphs.append(Paragraph(
            text=re.sub(r"\s+", " ", "\n".join(buffer)).strip(),
            line_start=line_offset + paragraph_start,
            line_end=line_offset + len(lines) - 1,
        ))
    return tuple(paragraphs)


def parse_freud(raw_text: str) -> tuple[list[Section], str]:
    body, body_offset = source_body(raw_text)
    roman_pattern = re.compile(r"^\s{20,}(I|II|III|IV|V|VI|VII|VIII)\s*$")
    headings: list[tuple[int, str]] = []
    for index, line in enumerate(body):
        match = roman_pattern.match(line)
        if match:
            headings.append((index, match.group(1)))
    expected = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
    if [roman for _, roman in headings[:8]] != expected:
        raise ValueError("Freud chapter structure changed")

    sections: list[Section] = []
    for position, (start, roman) in enumerate(headings[:7]):
        end = headings[position + 1][0]
        title_lines: list[str] = []
        cursor = start + 1
        while cursor < end and len(title_lines) < 3:
            value = body[cursor].strip()
            if value:
                if not value.isupper():
                    break
                title_lines.append(re.sub(r"\[[A-Z]+\]$", "", value).strip())
            elif title_lines:
                break
            cursor += 1
        title = " ".join(title_lines) or f"Chapter {roman}"
        section_lines = body[start:end]
        paragraphs = paragraphs_from_lines(section_lines, body_offset + start)
        if not paragraphs:
            raise ValueError(f"Freud chapter {roman} is empty")
        sections.append(Section(key=f"chapter-{position + 1:02d}", title=title,
                                paragraphs=paragraphs))

    clean_text = "\n\n".join(
        paragraph.text for section in sections for paragraph in section.paragraphs
    ).strip() + "\n"
    return sections, clean_text


MILLER_ENTRY = re.compile(r"^_([^_\n]{1,80})_\.(?:\[\d+\])?$", re.ASCII)


def parse_miller(raw_text: str) -> tuple[list[Section], str]:
    body, body_offset = source_body(raw_text)
    start = next(index for index, line in enumerate(body)
                 if line.strip() == "WHAT'S IN A DREAM.")
    end = next(index for index, line in enumerate(body[start + 1 :], start + 1)
               if line.strip() == "INDEX")
    entries: list[tuple[int, str]] = []
    for index in range(start, end):
        match = MILLER_ENTRY.match(body[index].strip())
        if match:
            entries.append((index, match.group(1).strip()))
    if len(entries) < 2_000:
        raise ValueError("Miller entry structure changed")

    sections: list[Section] = []
    slug_counts: dict[str, int] = {}
    for position, (entry_start, title) in enumerate(entries):
        entry_end = entries[position + 1][0] if position + 1 < len(entries) else end
        entry_lines = body[entry_start:entry_end]
        paragraphs = paragraphs_from_lines(entry_lines, body_offset + entry_start)
        if not paragraphs:
            raise ValueError(f"Miller entry {title!r} is empty")
        base = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or "entry"
        slug_counts[base] = slug_counts.get(base, 0) + 1
        suffix = f"-{slug_counts[base]}" if slug_counts[base] > 1 else ""
        sections.append(Section(key=f"entry-{base}{suffix}", title=title,
                                paragraphs=paragraphs))

    clean_text = "\n\n".join(
        paragraph.text for section in sections for paragraph in section.paragraphs
    ).strip() + "\n"
    return sections, clean_text


def split_paragraph(paragraph: Paragraph) -> list[Paragraph]:
    if len(paragraph.text) <= MAX_CHARS:
        return [paragraph]
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", paragraph.text)
                 if item.strip()]
    pieces: list[Paragraph] = []
    current: list[str] = []
    current_size = 0
    for sentence in sentences:
        if len(sentence) > MAX_CHARS:
            words = sentence.split()
            forced: list[str] = []
            forced_size = 0
            for word in words:
                if forced and forced_size + 1 + len(word) > MAX_CHARS:
                    pieces.append(Paragraph(" ".join(forced), paragraph.line_start,
                                            paragraph.line_end))
                    forced = []
                    forced_size = 0
                forced.append(word)
                forced_size += (1 if forced_size else 0) + len(word)
            if forced:
                sentence = " ".join(forced)
            else:
                continue
        separator = 1 if current else 0
        if current and current_size + separator + len(sentence) > MAX_CHARS:
            pieces.append(Paragraph(" ".join(current), paragraph.line_start,
                                    paragraph.line_end))
            current = []
            current_size = 0
        current.append(sentence)
        current_size += (1 if current_size else 0) + len(sentence)
    if current:
        pieces.append(Paragraph(" ".join(current), paragraph.line_start,
                                paragraph.line_end))
    return pieces


def chunk_section(section: Section) -> list[tuple[str, int, int]]:
    chunks: list[tuple[str, int, int]] = []
    current: list[Paragraph] = []
    current_size = 0
    expanded = [piece for paragraph in section.paragraphs for piece in split_paragraph(paragraph)]
    for paragraph in expanded:
        separator = 2 if current else 0
        if current and current_size + separator + len(paragraph.text) > MAX_CHARS:
            chunks.append(("\n\n".join(item.text for item in current),
                           current[0].line_start, current[-1].line_end))
            current = []
            current_size = 0
        current.append(paragraph)
        current_size += (2 if current_size else 0) + len(paragraph.text)
    if current:
        chunks.append(("\n\n".join(item.text for item in current),
                       current[0].line_start, current[-1].line_end))
    return chunks


def prepare_source(source: dict) -> dict:
    folder = MATERIAL_ROOT / source["source_id"]
    source_path = folder / "source.txt"
    raw_bytes = source_path.read_bytes()
    raw_text = raw_bytes.decode("utf-8")
    if source["kind"] == "freud_chapters":
        sections, clean_text = parse_freud(raw_text)
    else:
        sections, clean_text = parse_miller(raw_text)

    processed = folder / "processed"
    processed.mkdir(exist_ok=True)
    clean_path = processed / "clean.txt"
    chunks_path = processed / "chunks.jsonl"
    report_path = processed / "report.json"
    sample_path = processed / "sample-validation.json"
    clean_path.write_text(clean_text, encoding="utf-8", newline="\n")

    records: list[dict] = []
    for section in sections:
        for index, (text, line_start, line_end) in enumerate(chunk_section(section), 1):
            cross_reference_only = bool(re.search(r"\n\n\[\d+\]\s+See\b", text))
            quality_flags = []
            if len(text) < 100:
                quality_flags.append("short_source_entry")
            if cross_reference_only:
                quality_flags.append("cross_reference_only")
            records.append({
                "source_id": f"{source['source_id']}:{section.key}:{index:04d}",
                "book": source["book"],
                "author": source["author"],
                "translator": source["translator"],
                "chapter": section.title,
                "language": "en",
                "original_text": text,
                "source_line_start": line_start,
                "source_line_end": line_end,
                "source_file_sha256": sha256_bytes(raw_bytes),
                "source_url": source["source_url"],
                "rights_status": RIGHTS_STATUS,
                "verified": False,
                "retrieval_enabled": not cross_reference_only,
                "quality_flags": quality_flags,
            })
    if not records or any(not record["original_text"].strip() for record in records):
        raise ValueError(f"No valid chunks produced for {source['source_id']}")
    if any(len(record["original_text"]) > MAX_CHARS for record in records):
        raise ValueError(f"Oversized chunk produced for {source['source_id']}")
    record_hashes = [sha256_bytes(record["original_text"].encode("utf-8"))
                     for record in records]
    duplicate_count = len(record_hashes) - len(set(record_hashes))

    with chunks_path.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")

    lengths = [len(record["original_text"]) for record in records]
    report = {
        "source_id": source["source_id"],
        "source_file_sha256": sha256_bytes(raw_bytes),
        "section_count": len(sections),
        "chunk_count": len(records),
        "character_count": sum(lengths),
        "min_chunk_chars": min(lengths),
        "average_chunk_chars": round(mean(lengths), 2),
        "max_chunk_chars": max(lengths),
        "empty_chunk_count": 0,
        "duplicate_chunk_count": duplicate_count,
        "short_chunk_count": sum(
            "short_source_entry" in record["quality_flags"] for record in records
        ),
        "cross_reference_only_count": sum(
            "cross_reference_only" in record["quality_flags"] for record in records
        ),
        "retrieval_enabled_count": sum(record["retrieval_enabled"] for record in records),
        "max_allowed_chars": MAX_CHARS,
        "rights_status": RIGHTS_STATUS,
        "model_calls": 0,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    source_lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    sample_indexes = sorted({
        0,
        len(records) // 4,
        len(records) // 2,
        (len(records) * 3) // 4,
        len(records) - 1,
    })
    samples = []
    for index in sample_indexes:
        record = records[index]
        exact = record["original_text"] in clean_text
        if not exact:
            raise ValueError(f"Sample does not match clean text: {record['source_id']}")
        source_span = "\n".join(source_lines[
            record["source_line_start"] - 1:record["source_line_end"]
        ])
        normalized_source = re.sub(r"\s+", " ", source_span).strip()
        normalized_chunk = re.sub(r"\s+", " ", record["original_text"]).strip()
        source_match = normalized_chunk in normalized_source
        if not source_match:
            raise ValueError(f"Sample does not match source lines: {record['source_id']}")
        samples.append({
            "source_id": record["source_id"],
            "chapter": record["chapter"],
            "source_line_start": record["source_line_start"],
            "source_line_end": record["source_line_end"],
            "text_sha256": sha256_bytes(record["original_text"].encode("utf-8")),
            "exact_match_clean": True,
            "normalized_match_source_lines": True,
        })
    sample_path.write_text(json.dumps({"samples": samples}, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return report


def main() -> None:
    reports = [prepare_source(source) for source in SOURCES]
    for report in reports:
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
