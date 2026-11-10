
import json
import math
import requests
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"

TIMESTAMPS = OUTPUT / "timestamps.json"
STORYBOARD = OUTPUT / "visual_storyboard.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3:4b"

# Visual editing configuration
TARGET_SCENE_SECONDS = 5.0
MAX_SCENE_SECONDS = 8.0

SCENE_TYPES = [
    "stock_footage",
    "animated_text",
    "diagram",
    "timeline",
    "statistic"
]


def load_words():
    if not TIMESTAMPS.exists():
        raise FileNotFoundError(TIMESTAMPS)

    words = json.loads(
        TIMESTAMPS.read_text(encoding="utf-8")
    )

    if not words:
        raise RuntimeError("No narration words found.")

    return words


def build_scenes(words):
    scenes = []
    current = []

    for word in words:
        if not current:
            current.append(word)
            continue

        start = float(current[0]["start"])
        end = float(word["end"])
        elapsed = end - start

        # Split close to natural punctuation,
        # while limiting maximum scene duration.
        previous = current[-1]["word"].strip()
        natural_break = previous.endswith(
            (".", "!", "?", ";", ":")
        )

        if (
            elapsed >= MAX_SCENE_SECONDS
            or (
                elapsed >= TARGET_SCENE_SECONDS
                and natural_break
            )
        ):
            scenes.append(current)
            current = []

        current.append(word)

    if current:
        scenes.append(current)

    return scenes


def generate_direction(narration):
    prompt = f"""
You are the visual director of a professional
educational YouTube documentary.

Your job is to decide how to illustrate this narration.

NARRATION:
{narration}

CHOOSE ONE VISUAL TYPE:

stock_footage:
Use real-world video footage for atmosphere,
environments, people or physical activity.

animated_text:
Use bold animated words or a short key phrase.

diagram:
Explain a concept using simple labelled
objects, nodes, arrows or a process.

timeline:
Show an ordered sequence of events or stages.

statistic:
Highlight a numeric fact that is explicitly
present in the narration.

IMPORTANT RULES:
- Prefer clarity over flashy visuals.
- Don't invent statistics, dates or events.
- Don't treat stock footage as real evidence.
- Text must be short and readable.
- Only select "statistic" if the narration
  actually includes a verifiable number.
- For diagrams, return clear visual components.
- Avoid excessive stock footage.
- Use only facts present in the narration.
- No extra explanations outside the JSON.

Return a JSON object with these exact keys:

{{
  "visual_type": "diagram",
  "on_screen_text": "Short heading",
  "visual_description": "What the viewer sees",
  "animation": "How the visual appears or moves",
  "stock_search": "Short stock video search query",
  "elements": ["element one", "element two"]
}}

Keep the response concise.
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 450
            }
        },
        timeout=600
    )

    response.raise_for_status()
    result = json.loads(response.json()["response"])

    if not isinstance(result, dict):
        raise ValueError("Invalid AI storyboard response.")

    visual_type = result.get("visual_type")

    if visual_type not in SCENE_TYPES:
        visual_type = "animated_text"

    text = str(
        result.get("on_screen_text") or ""
    ).strip()[:65]

    description = str(
        result.get("visual_description") or ""
    ).strip()[:350]

    animation = str(
        result.get("animation") or ""
    ).strip()[:200]

    search = str(
        result.get("stock_search") or ""
    ).strip()[:100]

    elements = result.get("elements", [])

    if not isinstance(elements, list):
        elements = []

    elements = [
        str(item)[:60]
        for item in elements[:6]
    ]

    return {
        "visual_type": visual_type,
        "on_screen_text": text,
        "visual_description": description,
        "animation": animation,
        "stock_search": search,
        "elements": elements
    }


def main():
    words = load_words()
    scene_groups = build_scenes(words)

    print("=" * 50)
    print("AI VISUAL DIRECTOR")
    print("=" * 50)
    print(f"Narration scenes: {len(scene_groups)}")

    storyboard = []

    for index, group in enumerate(
        scene_groups, start=1
    ):
        narration = " ".join(
            str(word["word"]).strip()
            for word in group
        )

        start = float(group[0]["start"])
        end = float(group[-1]["end"])

        print(
            f"\nPlanning scene {index}/"
            f"{len(scene_groups)}...",
            flush=True
        )

        try:
            direction = generate_direction(
                narration
            )

        except Exception as error:
            print(f"AI direction failed: {error}")

            direction = {
                "visual_type": "animated_text",
                "on_screen_text": "",
                "visual_description":
                    "Readable narration title graphic",
                "animation": "Simple fade",
                "stock_search": "",
                "elements": []
            }

        scene = {
            "scene": index,
            "start": round(start, 3),
            "end": round(end, 3),
            "narration": narration,
            **direction
        }

        storyboard.append(scene)

        # Save after each scene so a failure
        # doesn't lose previous progress.
        STORYBOARD.write_text(
            json.dumps(
                storyboard,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        print(
            f"  Type: {direction['visual_type']}"
        )
        print(
            f"  Visual: "
            f"{direction['visual_description']}"
        )

    print("\nVISUAL STORYBOARD COMPLETE")
    print(f"Saved to: {STORYBOARD}")

    print("\nSCENE TYPE SUMMARY:")

    for scene_type in SCENE_TYPES:
        count = sum(
            1 for scene in storyboard
            if scene["visual_type"] == scene_type
        )

        print(f"{scene_type}: {count}")


if __name__ == "__main__":
    main()
