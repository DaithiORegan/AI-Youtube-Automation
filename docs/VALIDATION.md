# Validation record — 13 November 2026

## Completed

- **41 tests passed** on Python 3.12 in the managed Linux environment.
- Real FFmpeg integration: multi-shot export, camera-filter execution, caption burning, music sidechain ducking, two-pass normalisation, delivered loudness/true-peak measurement and complete decode.
- Cache reuse, changed-text/audio/art invalidation, missing/undersized art rejection, project locks and stale-review rejection.
- HTTP contract tests against deterministic local stand-ins for Ollama and ComfyUI: draft/revision payloads, model unloading, native image workflow submission, polling, PNG retrieval, failure handling and per-shot image caching. These test the integrations, not the artistic output of a real model.
- Real Kokoro model/voice downloads from the official ONNX release and a successful speech synthesis using `af_heart`. Audio data was created and checked; this does not establish subjective narration quality for every script.
- Dashboard Chromium checks: desktop layout, local setup health, missing-Ollama recovery, mobile overflow and absence of JavaScript page errors.
- The generated review page's MP4 preview loaded and played in Chromium through the local server.
- JavaScript syntax, Python compilation and Python wheel build passed.

## Requires your Windows/GPU

This environment has **no NVIDIA GPU**, no running Ollama story model and no real ComfyUI installation/checkpoint. Therefore a complete AI-illustrated film, SDXL art quality, recurring-character consistency, GPU memory behaviour and end-to-end production time have **not** been validated on your RTX 3060 Ti. The Windows batch launchers were prepared and reviewed but were not executed on Windows here.

The supplied procedural-image/test-tone demo is explicitly labelled technical-only and cannot be approved. It is not presented as a finished sample video or as evidence that the AI illustrations are high quality.

No Google authentication, YouTube channel creation, upload, publication or monetisation decision occurred. The workflow prepares local files and requires an editorial review. Official YouTube disclosure and monetisation guidance was consulted, but software cannot guarantee compliance or eligibility.

Start with the prepared seven-shot pilot, review the generated visuals on your actual hardware, and adjust the art direction before investing in a long episode.
