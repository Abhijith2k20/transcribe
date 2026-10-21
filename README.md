# Indic Transcriber

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Abhijith2k20/transcribe/blob/main/launcher.ipynb)

A free, one-click transcription tool. The badge opens a Colab notebook that loads a speech model onto Colab's free GPU and prints a link. That link opens a web page where you drop in audio or video files and get transcripts back. Tamil, Malayalam, Hindi, Kannada, English, or a mix: each comes back in the script it was spoken in.

## First-time setup

1. Click **Open in Colab** above.
2. **Runtime → Change runtime type → T4 GPU**.
3. Make a Hugging Face **read** token at <https://huggingface.co/settings/tokens>. In Colab, click the key icon (Secrets) on the left, add a secret named `HF_TOKEN`, and turn on **Notebook access**.
4. With the same Hugging Face account, accept the licenses at
   [indic-transcribe-flex](https://huggingface.co/bodhan-ai/indic-transcribe-flex) and
   [indic-transcribe-core](https://huggingface.co/bodhan-ai/indic-transcribe-core).

## Every time

**Runtime → Run all.** Click **Run anyway** if Colab warns about the notebook, and allow secret access. After a few minutes a big **Open the transcriber** button appears at the bottom. Keep the Colab tab open while you use the page.

## Engines

| Engine | Use it for |
|---|---|
| Indic-Transcribe Flex (default) | Indian languages and code-mixed speech. "Keep in English" leaves English words in Latin script. |
| Indic-Transcribe Core | Highest accuracy on single-language Indian audio. English words come out in the native script. |
| Whisper large-v3 | Pure English and non-Indian languages. Weak on mixed speech. Set `TRANSCRIBER_WHISPER_MODEL=large-v3-turbo` for a faster model. |

## Limits

- Runs only while your Colab session runs. Free sessions end after a few hours, or sooner when idle, and GPUs aren't always available.
- Files up to 100 MB each (the free Cloudflare tunnel's limit). Convert big videos to mp3 first.
- Transcripts live only for the session. Download what you want to keep.

## Local development (no GPU)

```sh
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
TRANSCRIBER_ENGINE=mock .venv/bin/python -m transcriber.launch --no-tunnel   # http://localhost:8000
.venv/bin/python -m pytest
```

Needs `ffmpeg` on your PATH.

## Licensing and credits

- **Built with Indic-Transcribe from Bodhan AI / AI4Bharat**, under the Indic Open Model License v1.0. Free for personal and commercial use, but running it as a hosted service for other people needs Bodhan AI's written permission. This tool is for your own use.
- Whisper (OpenAI) via faster-whisper: MIT.
- Anek typeface by Ek Type: SIL Open Font License.
- Google Colab's free tier is for interactive use, not public web services. Keep this a personal tool.
