"""Bold word-by-word ASS captions and a hook title for the opening seconds."""

from __future__ import annotations

from app.edit import remap_words
from app.transcript import Word

PRESETS = {
    "hormozi": {
        "font": "Anton",
        "uppercase": True,
        "active": "&H0000FFFF&",
        "base": "&H00FFFFFF&",
        "outline": 7,
        "shadow": 0,
        "size_ratio": 0.064,
        "title_ratio": 0.052,
        "spacing": 1,
    },
    "pop": {
        "font": "Anton",
        "uppercase": True,
        "active": "&H00365AFF&",
        "base": "&H00FFFFFF&",
        "outline": 7,
        "shadow": 0,
        "size_ratio": 0.060,
        "title_ratio": 0.050,
        "spacing": 1,
    },
    "clean": {
        "font": "Inter",
        "uppercase": False,
        "active": "&H004AFFD6&",
        "base": "&H00F4F1EA&",
        "outline": 3,
        "shadow": 1,
        "size_ratio": 0.046,
        "title_ratio": 0.040,
        "spacing": 0,
    },
}


def build_ass(
    words: list[Word],
    *,
    segments: list[tuple[float, float]],
    xfade: float,
    style: str,
    title: str,
    width: int,
    height: int,
    title_seconds: float = 2.6,
) -> str:
    preset = PRESETS.get(style.lower(), PRESETS["hormozi"])
    timed = remap_words(words, segments, xfade)
    font_size = max(28, int(height * preset["size_ratio"]))
    title_size = max(24, int(height * preset["title_ratio"]))
    caption_margin = int(height * 0.17)
    title_margin = int(height * 0.075)
    events = _events(timed, preset, title, title_seconds)
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{preset["font"]},{font_size},{preset["base"]},&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,{preset["spacing"]},0,1,{preset["outline"]},{preset["shadow"]},2,70,70,{caption_margin},1
Style: Title,{preset["font"]},{title_size},&H00FFFFFF,&H000000FF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,8,0,8,48,48,{title_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{events}
"""


def _events(
    words: list[Word],
    preset: dict,
    title: str,
    title_seconds: float,
) -> str:
    lines: list[str] = []
    shown_title = _present(title, preset["uppercase"])
    if shown_title:
        hold = title_seconds
        if words:
            hold = min(title_seconds, max(1.4, words[-1].end))
        lines.append(
            f"Dialogue: 0,{_ass_time(0)},{_ass_time(hold)},Title,,0,0,0,,{{\\fad(70,180)}}{_escape(shown_title)}"
        )
    for page in _pages(words):
        for index, word in enumerate(page):
            end = page[index + 1].start if index + 1 < len(page) else max(word.end, word.start + 0.18)
            if end <= word.start:
                end = word.start + 0.18
            text = _colorize(page, index, preset)
            lines.append(
                f"Dialogue: 0,{_ass_time(word.start)},{_ass_time(end)},Caption,,0,0,0,,{text}"
            )
    return "\n".join(lines)


def _pages(words: list[Word], per_page: int = 3, gap: float = 0.45) -> list[list[Word]]:
    pages: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current and (word.start - current[-1].end > gap or len(current) >= per_page):
            pages.append(current)
            current = []
        current.append(word)
    if current:
        pages.append(current)
    return pages


def _colorize(page: list[Word], active: int, preset: dict) -> str:
    chunks: list[str] = []
    for index, word in enumerate(page):
        color = preset["active"] if index == active else preset["base"]
        shown = _present(word.text, preset["uppercase"])
        chunks.append(f"{{\\c{color}}}{_escape(shown)}")
    return " ".join(chunks)


def _present(text: str, uppercase: bool) -> str:
    cleaned = " ".join(text.split())
    if uppercase:
        return cleaned.upper()
    return cleaned


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, centiseconds = divmod(centiseconds, 360000)
    minutes, centiseconds = divmod(centiseconds, 6000)
    whole, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02d}:{whole:02d}.{centiseconds:02d}"
