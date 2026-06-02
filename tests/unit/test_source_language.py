from __future__ import annotations

from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "mcp_conductor"
CJK_RANGES = (
    ("\u3400", "\u4dbf"),
    ("\u4e00", "\u9fff"),
)


def has_cjk(text: str) -> bool:
    return any(start <= character <= end for character in text for start, end in CJK_RANGES)


def test_python_source_uses_english_text() -> None:
    offenders: list[str] = []
    for source_file in SOURCE_ROOT.rglob("*.py"):
        lines = source_file.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if has_cjk(line):
                offenders.append(
                    f"{source_file.relative_to(SOURCE_ROOT)}:{line_number}: {line.strip()}"
                )

    assert offenders == []
