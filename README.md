# Storyforge — your local illustrated-fiction studio

This repository now has a complete **fiction-first production path** alongside the original stock-footage documentary scripts. It is designed for Windows 11, 32 GB RAM and an RTX 3060 Ti, using local tools with no paid generation APIs.

**Start with a 60–90 second pilot.** The pipeline creates illustrated story films: generated still illustrations with camera motion, narration and editing. It does not create continuous character animation. A convincing first film still requires reviewing the art and listening to the narration; neither code nor an AI label guarantees artistic quality, YouTube compliance or monetisation.

[Studio preview](docs/images/studio-desktop.png) · [Mobile preview](docs/images/studio-mobile.png) · [What was tested](docs/VALIDATION.md)

## Start on Windows

Follow **[Windows: first film in one session](docs/WINDOWS_FIRST_FILM.md)**. The short version:

1. Install Python 3.12 and FFmpeg; clone/download this repository.
2. Double-click **`SETUP_WINDOWS.bat`**. It installs project dependencies and downloads the local Kokoro voice files, approximately 350 MiB.
3. Install the official NVIDIA portable ComfyUI bundle and an SDXL checkpoint as described in the guide. Use **`START_COMFY_LOW_VRAM.bat`** for the documented folder layout.
4. Double-click **`START_STUDIO.bat`**. Your browser opens **http://127.0.0.1:8787**.
5. Select **Try the prepared original pilot**. This uses a supplied original story and does not need Ollama. New premises use local Ollama; install it and run `ollama pull qwen3:4b` when ready.

The prepared film is **The Parcel That Spoke in Her Own Voice**, a seven-shot fictional story about a courier who hears forgotten promises. It uses original characters and writing, rather than reproducing the reference channel's mascot, thumbnails or scripts.

## What changed

| Previously | New studio workflow |
| --- | --- |
| Hard-coded Windows interpreter path | Current interpreter; Windows launchers and portable Python CLI |
| Narration, music and catalogue had to exist before starting | New story → per-scene narration → per-scene illustration → motion → audio master → review |
| Documentary stock clips selected after narration | Story and visual plan created together; original character and style bibles |
| Missing clips could become dark fallback screens | Missing/undersized art stops production with a specific next step |
| One large FFmpeg graph with many inputs | Individual cached shots, then a lightweight assembly pass |
| Fixed stock-music dependency | Music optional; supplied tracks require a rights note and are ducked under speech |
| Basic volume setting | Two-pass loudness normalisation, true-peak target, 48 kHz AAC audio |
| No launch instructions or test suite | Studio health check, setup scripts, tests and CI |
| No editorial handoff | Contact sheet, thumbnail candidate, script, captions, review page, upload metadata and hash-bound approval |

## Production, step by step

- **Write:** a local Ollama draft and an editorial revision. Story validation requires a hook, a reversal and a payoff, consecutive scene IDs and bounded narration. This is a useful structural check, not a substitute for reading the story.
- **Direct:** each shot has a specific subject, emotion, setting, composition and camera move. The same character/style descriptions are included in every image prompt.
- **Narrate:** Kokoro runs locally on CPU. Utterances retain sentence phrasing; short fades prevent clicks. Scene audio is measured and cached independently.
- **Illustrate:** a native-node ComfyUI SDXL workflow, one image at a time. Ollama unloads after writing; ComfyUI releases models after illustration to reduce GPU competition. Seeds and prompts are recorded.
- **Edit:** subtle pushes, pulls and pans, deliberate cuts, per-shot caching and frame-quantised audio pauses to prevent cumulative sync drift. Rendering uses CPU H.264 so it does not compete with the diffusion model for VRAM.
- **Finish:** optional music ducking, two-pass −16 LUFS / −1.5 dBTP target, AAC at 48 kHz, H.264/yuv420p with fast-start metadata, full-file decode and dimension/duration checks.
- **Review:** inspect the contact sheet and watch the whole film. Review faces, clothing, hands, incidental text, crops, pronunciations, captions and story coherence. Fix/re-generate specific shots, resume, and record the review.

Captions use measured speech-chunk boundaries, with estimated timing inside a chunk. They are **not word-forced-aligned**. Sidecar SRT/VTT is the default; burned-in captions are optional. Check captions before uploading.

Character descriptions and seeds help consistency, but do **not** guarantee identity across generated shots. A reference-image/IP-Adapter pipeline, custom animation engine and lip-sync are not included. Manually replace weak shots or use a separately licensed illustration workflow when needed.

## CLI

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux instead: source .venv/bin/activate
python -m pip install -e ".[voice,test]"
python -m studio models
python -m studio doctor
python -m studio serve
```

Prepared pilot:

```bash
python -m studio pilot --project projects/first-film
python -m studio run projects/first-film/project.json
```

New story, after Ollama is installed/running:

```bash
python -m studio create --topic "A city lets everyone borrow one hour from their future. A clock repairer discovers who pays it back." --seconds 90 --project projects/borrowed-hour
python -m studio run projects/borrowed-hour/project.json
```

Run individual stages or render a 640×360 preview:

```bash
python -m studio voice projects/first-film/project.json
python -m studio images projects/first-film/project.json
python -m studio render projects/first-film/project.json --preview
python -m studio render projects/first-film/project.json
python -m studio package projects/first-film/project.json
```

The dashboard's Resume action runs all stages but reuses unchanged cached voice, images and clips. If you intend to preserve custom recorded scene audio, run `render` and `package` directly rather than `run`, which generates narration. For externally made images, set a scene's `art_source` to `manual` and place its image at `art/001.png` etc.; the image stage will preserve it. Missing manual art causes a clear stop.

## Project settings and outputs

Each project is an ordinary editable `project.json`. See [the prepared template](studio/data/first-film.json). Settings include the local model names, narrator, speed, seed, image dimensions, output resolution, encoder preset, music path and captions choice. A ComfyUI checkpoint filename must match its local dropdown exactly, including any subdirectory. New generation endpoints are restricted to local HTTP origins.

Outputs live under `projects/<project>/` and are Git-ignored:

- `final.mp4`, or `preview.mp4` for a preview render.
- `audio/` and `art/`: numbered scene assets.
- `captions.srt`, `captions.vtt`, `script.txt`, `art-prompts.txt`.
- `contact-sheet.jpg`, `thumbnail.jpg`: visual review assets. The thumbnail is an art crop, not an optimised click-through promise.
- `review.html`, `upload-metadata.json`, `quality.json`.
- Cache/provenance records, current stage status and optional `approval.json`.

For music, set `settings.music` to the full local path and `settings.music_rights` to the ownership/licence note. Silence under narration is the default; no unlicensed song or generated “copyright-free” claim is inserted automatically. Review the resulting mix on headphones and speakers.

Only one production runs at a time in the dashboard. A per-project file lock prevents simultaneous CLI/dashboard writes to that project. If a process is forcibly terminated, verify it has stopped before deleting its stale `.production.lock`. Check ComfyUI's queue before resuming an interrupted image job; an in-flight request can continue in that service.

## Publishing

Read **[YouTube, rights and editorial review](docs/YOUTUBE_REVIEW.md)**. The app prepares a private-upload handoff and never uploads or publishes by itself. It does not create or configure your YouTube channel, authenticate to Google, or promise monetisation.

You can record a completed review through the dashboard, or copy `examples/review-checklist.json`, set each item to true **after doing it**, and run:

```bash
python -m studio approve projects/first-film/project.json --checklist path/to/completed-review.json
```

Approval is tied to the exported master, project and scene assets. Editing them requires rendering/reviewing again. It is a recorded human decision, not an automated compliance certificate.

## Testing and limitations

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m studio demo --directory artifacts/technical-demo
```

The demo contains procedural shapes and test tones, is labelled **not for publication**, and cannot be approved. It tests the renderer without large model downloads. See [validation](docs/VALIDATION.md) for what was run versus what still needs your Windows/GPU.

The old documentary path remains at `legacy_pipeline.py`. It needs the original recording/catalogue/Pixabay/music setup and optional `.[legacy,voice]` dependencies. Its dark-screen fallback has been removed. The new fiction path does not use Pixabay or require an API key. The older standalone scripts are preserved for compatibility, not presented as the recommended new production workflow.
