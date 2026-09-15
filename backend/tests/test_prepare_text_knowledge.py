from scripts.prepare_text_knowledge import (
    MAX_CHARS,
    Paragraph,
    Section,
    chunk_section,
    parse_miller,
    source_body,
)


def test_source_body_excludes_gutenberg_wrapper():
    raw = "header\n*** START OF THE PROJECT GUTENBERG EBOOK TEST ***\nbody\n*** END OF THE PROJECT GUTENBERG EBOOK TEST ***\nfooter"
    lines, offset = source_body(raw)
    assert lines == ["body"]
    assert offset == 3


def test_chunk_section_never_crosses_limit():
    section = Section("test", "Test", (
        Paragraph("a" * 2_000, 1, 2),
        Paragraph("b" * 1_000, 3, 4),
    ))
    chunks = chunk_section(section)
    assert len(chunks) == 2
    assert all(len(text) <= MAX_CHARS for text, _, _ in chunks)
    assert chunks[0][1:] == (1, 2)
    assert chunks[1][1:] == (3, 4)


def test_miller_entries_remain_separate():
    headings = "\n".join(f"_Entry {index}_.\n\nText {index}.\n" for index in range(2_001))
    raw = (
        "*** START OF THE PROJECT GUTENBERG EBOOK TEST ***\n"
        "WHAT'S IN A DREAM.\n\n" + headings + "\nINDEX\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK TEST ***"
    )
    sections, clean = parse_miller(raw)
    assert len(sections) == 2_001
    assert sections[0].title == "Entry 0"
    assert sections[-1].title == "Entry 2000"
    assert "INDEX" not in clean
