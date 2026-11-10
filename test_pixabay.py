
import os
import requests
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("PIXABAY_API_KEY")

if not key:
    raise RuntimeError("Missing Pixabay API key in .env")

response = requests.get(
    "https://pixabay.com/api/videos/",
    params={
        "key": key,
        "q": "computer technology",
        "per_page": 5
    },
    timeout=30
)

response.raise_for_status()

data = response.json()

print(f"Total matching videos: {data['totalHits']}")

for video in data["hits"]:
    print(f"Video ID: {video['id']}")
    print(f"Tags: {video['tags']}")
    print(f"Duration: {video['duration']} seconds")
    print("---")
