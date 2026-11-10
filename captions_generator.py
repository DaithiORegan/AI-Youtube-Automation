
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
TIMESTAMPS = OUTPUT / "timestamps.json"
CAPTIONS = OUTPUT / "captions.ass"

# Caption appearance
FONT = "Arial"
FONT_SIZE = 64
BOTTOM_MARGIN = 145

# Phrase settings
MAX_WORDS = 4
MAX_CHARACTERS = 28
MAX_DURATION = 2.6
MAX_GAP = 0.55

# ASS colours use BGR ordering
WHITE = "&H00FFFFFF&"
YELLOW = "&H001AD2FF&"
BLACK = "&H00000000&"


def ass_time(seconds):
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)

    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def clean_text(value):
    return (
        str(value)
        .replace("\\", "")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\n", " ")
        .strip()
    )


def group_words(words):
    groups = []
    current = []

    for word in words:
        text = clean_text(word["word"])
        start = float(word["start"])
        end = float(word["end"])

        if not text or end <= start:
            continue

        item = {
            "word": text,
            "start": start,
            "end": end
        }

        if current:
            gap = start - current[-1]["end"]
            proposed = current + [item]

            phrase = " ".join(w["word"] for w in proposed)
            length = end - current[0]["start"]

            should_split = (
                len(current) >= MAX_WORDS
                or len(phrase) > MAX_CHARACTERS
                or length > MAX_DURATION
                or gap > MAX_GAP
            )

            if should_split:
                groups.append(current)
                current = []

        current.append(item)

    if current:
        groups.append(current)

    return groups


def highlighted_phrase(group, active_index):
    parts = []

    for index, item in enumerate(group):
        word = item["word"]

        if index == active_index:
            word = (
                r"{\1c" + YELLOW + r"\b1}"
                + word
                + r"{\1c" + WHITE + r"\b0}"
            )

        parts.append(word)

    return " ".join(parts)


def create_ass(groups):
    header = f"""[Script Info]
Title: YouTubeAI Professional Captions
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{FONT},{FONT_SIZE},{WHITE},{YELLOW},{BLACK},{BLACK},-1,0,0,0,100,100,0,0,1,4,1,2,120,120,{BOTTOM_MARGIN},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    for group_index, group in enumerate(groups):
        for index, item in enumerate(group):
            start = item["start"]

            if index + 1 < len(group):
                end = group[index + 1]["start"]
            else:
                end = item["end"]

                if group_index + 1 < len(groups):
                    next_start = groups[group_index + 1][0]["start"]
                    end = min(end + 0.12, next_start)

            end = max(start + 0.05, end)

            phrase = highlighted_phrase(group, index)

            # Soft fade in/out for the phrase.
            if index == 0:
                phrase = r"{\fad(70,0)}" + phrase
            elif index == len(group) - 1:
                phrase = r"{\fad(0,70)}" + phrase

            events.append(
                "Dialogue: 0,"
                f"{ass_time(start)},"
                f"{ass_time(end)},"
                f"Main,,0,0,0,,{phrase}"
            )

    return header + "\n".join(events) + "\n"


def main():
    if not TIMESTAMPS.exists():
        raise FileNotFoundError(TIMESTAMPS)

    words = json.loads(
        TIMESTAMPS.read_text(encoding="utf-8")
    )

    if not words:
        raise RuntimeError("No timestamped words found.")

    groups = group_words(words)

    OUTPUT.mkdir(parents=True, exist_ok=True)

    CAPTIONS.write_text(
        create_ass(groups),
        encoding="utf-8-sig"
    )

    print("PROFESSIONAL CAPTIONS GENERATED")
    print(f"Words: {sum(len(g) for g in groups)}")
    print(f"Caption phrases: {len(groups)}")
    print(f"Saved: {CAPTIONS}")


if __name__ == "__main__":
    main()
