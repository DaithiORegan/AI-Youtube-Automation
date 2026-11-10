
import requests
from pathlib import Path
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3:4b"

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

TOPIC = "How Hackers Shut Down Billion-Dollar Companies"

PROMPT = f"""
You are a professional YouTube documentary scriptwriter.

Write an original, engaging documentary script about:
{TOPIC}

Requirements:
- Target approximately 800 words.
- Start with a compelling hook.
- Use a professional, conversational narration style.
- Explain complex topics clearly.
- Include a strong introduction, middle and conclusion.
- Write only words intended to be spoken by the narrator.
- Do not include timestamps, stage directions or camera instructions.
- Do not invent specific incidents, dates or statistics.
- If a fact needs verification, mark it [VERIFY].
- Avoid repetitive language and generic filler.
- Do not include internal reasoning or commentary.
"""

print("Generating YouTube script with local AI...")

response = requests.post(
    OLLAMA_URL,
    json={
        "model": MODEL,
        "prompt": PROMPT,
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 1800
        }
    },
    timeout=600
)

response.raise_for_status()

script = response.json()["response"].strip()

if not script:
    raise RuntimeError("Ollama returned an empty script.")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = OUTPUT_DIR / f"script_{timestamp}.txt"

filename.write_text(script, encoding="utf-8")

print("\nSCRIPT GENERATED SUCCESSFULLY")
print(f"Saved to: {filename.resolve()}")
print(f"Word count: {len(script.split())}")
