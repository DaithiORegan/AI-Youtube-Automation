# Windows 11 / RTX 3060 Ti: first film

Your 32 GB RAM and RTX 3060 Ti are a sensible starting point for local illustrated fiction. Most 3060 Ti cards have 8 GB VRAM. Run the models sequentially and begin with a short pilot rather than a 10–20 minute episode.

Allow **20–30 GB free disk space**. First-time downloads and internet speed may dominate setup time; a finished film within one or two hours is a target, not a guarantee. This code cannot install or run software on your home PC from the cloud session.

## 1. Get the updated code

If already cloned, save any local work, then pull the updated branch/version linked in the handoff. Otherwise download the repository ZIP from GitHub and extract it to a writable folder, e.g. `C:\Storyforge`. Avoid OneDrive-synchronised folders and protected Program Files paths for model/render working data.

## 2. Python and FFmpeg

Install [Python 3.12](https://www.python.org/downloads/) with the Python launcher enabled. Install a complete [FFmpeg build](https://ffmpeg.org/download.html) that includes libx264, libass, loudnorm and zoompan, and add its `bin` directory to PATH. The Windows package manager alternative is:

```powershell
winget install --id Python.Python.3.12 -e
winget install --id Gyan.FFmpeg -e
```

Close and reopen your terminal after installation. Verify:

```powershell
py -3.12 --version
ffmpeg -version
ffprobe -version
```

Double-click **SETUP_WINDOWS.bat**. It creates the virtual environment, installs the free local narration dependencies and downloads the two voice files from the official Kokoro ONNX release. This requires no API key. It does not silently install drivers, Ollama, ComfyUI or a 7 GB image checkpoint.

## 3. ComfyUI and the illustration model

1. Download the official **NVIDIA portable Windows** bundle from [ComfyUI releases](https://github.com/Comfy-Org/ComfyUI/releases). Use a bundle compatible with your NVIDIA driver; update the driver from NVIDIA if required. Extract with 7-Zip.
2. Put its folder here if you want the supplied launcher:

   `C:\Storyforge\tools\ComfyUI_windows_portable\`

   That folder should contain `python_embeded\python.exe` and `ComfyUI\main.py`. If using an existing ComfyUI install, keep it and launch it normally with `--lowvram`.
3. Review the [official SDXL base model card and licence](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0). Download **sd_xl_base_1.0.safetensors** (roughly 7 GB).
4. Put that file in:

   `tools\ComfyUI_windows_portable\ComfyUI\models\checkpoints\`

5. Double-click **START_COMFY_LOW_VRAM.bat**. Wait until ComfyUI is serving **http://127.0.0.1:8188**. Leave its console open.

No custom ComfyUI nodes, paid models, accounts or unofficial video-generation APIs are required. A different SDXL-compatible illustration checkpoint may yield better art, but must be reviewed for licence terms and selected by its exact local filename. SD1.5, Flux and video checkpoints are not interchangeable with this supplied SDXL workflow.

## 4. Make the prepared pilot

Double-click **START_STUDIO.bat**. The studio opens at **http://127.0.0.1:8787**.

Click **Check setup**, then **Try the prepared original pilot**. A missing Ollama warning can be ignored **for this prepared story only**; it still needs voice models, FFmpeg and ComfyUI. The pilot has seven scene illustrations, approximately a minute to a minute and a half of narration depending on voice pacing, a contact sheet and a review page.

The first local AI image and first voice load take longer. Subsequent scenes reuse loaded models. The console and dashboard show the current step. Do not start several productions or large games concurrently on the GPU.

If image generation runs out of VRAM, close GPU-heavy apps and restart ComfyUI in low-VRAM mode. As a fallback, edit the project's `settings.image_width`/`image_height` to **1024 / 576**, reduce `steps` to **20**, and resume. The default is **1344 / 768**, producing approximately one-megapixel illustrations upscaled/cropped into the 1920×1080 export; this is not native 1080p detail.

If faces/clothing change between shots, revise individual `image_prompt` descriptions, then resume. Only images whose prompt/seed/settings changed are regenerated; affected video clips are rebuilt. A fixed character description is helpful but not a true identity-control system. Do not publish obviously inconsistent or malformed shots.

## 5. Add local story writing

Install [Ollama](https://ollama.com/download/windows), start it and run:

```powershell
ollama pull qwen3:4b
```

If installed through winget:

```powershell
winget install --id Ollama.Ollama -e
```

Reopen your terminal if needed. Ollama should serve **http://127.0.0.1:11434**. Keep it running. In the studio, enter a new fiction premise and click **Create my film**. The writer drafts and revises the story, unloads its model, then hands the GPU to ComfyUI.

## 6. Review and upload

Open **Review film** in the studio. Watch the full film. Check character continuity, illustrations, narration, captions, pacing and the ending. Music is optional; add only a track you own or are licensed to use, with a rights note in project settings.

Create your channel through [YouTube Studio](https://studio.youtube.com/) if needed. Upload `final.mp4` privately first, use `thumbnail.jpg` as a candidate, attach `captions.srt`, and adapt the prepared title/description. Review the audience and synthetic-content questions yourself. After YouTube finishes processing, inspect playback and any copyright/restriction notices before making the film public.

For the first two hours, the goal is **one reviewed pilot**, not a fully automated publishing schedule. Once the format works, longer films and repeat production become much easier to judge and improve.

## Common stops

| Message | Next step |
| --- | --- |
| Python not found / unsupported version | Install Python 3.12, reopen terminal, rerun setup |
| FFmpeg not found | Add FFmpeg `bin` to PATH, reopen the studio |
| Kokoro model missing | Rerun SETUP_WINDOWS.bat or `.venv\Scripts\python.exe -m studio models` |
| Ollama unavailable | Start Ollama; use the prepared pilot if writing is not set up yet |
| Checkpoint not found | Verify filename, SDXL compatibility and ComfyUI checkpoint folder; restart ComfyUI |
| Image generation timeout | Inspect ComfyUI console/queue; a job may still be running before you resume |
| Missing illustration / low resolution | Generate or replace that scene's PNG; blank scenes are not substituted |
| Stale production lock | Confirm the old process is gone, delete the project's `.production.lock`, then resume |
| Story validation failed | Try a simpler premise or inspect/edit the model's project structure; no silent generic script is substituted |
