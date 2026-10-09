# Spool

Spool turns a long video into short, vertical clips for TikTok, YouTube Shorts, and Reels. It runs on your machine. Transcription never leaves it. Highlight picking uses Gemini Flash when you set a key, and a local ranker when you do not.

## What it does

1. You drop in a long video (an hour is fine).
2. [faster-whisper](https://github.com/SYSTRAN/faster-whisper) transcribes it with word timestamps.
3. An LLM, or the built-in ranker, picks 15–60s moments with a hook score, a reason, a title, and a mood.
4. FFmpeg cuts each moment, reframes it to 9:16, and follows a face or the moving subject. If neither shows up, it center-crops.
5. Silences and filler words (`um`, `you know`, …) become jump cuts. Emphasis words get a short punch-in. The mood picks a transition: slide, flash, wipe, or fade.
6. Word-by-word captions burn in, with the hook title on screen for the opening seconds. Three presets: Hormozi, Pop, and Clean.
7. The gallery previews each clip. Download the mp4, or an [MLT](https://www.mltframework.org/) project you can open in Kdenlive or Shotcut.

## Mac setup

You need Apple Silicon or any recent Mac, plus [Homebrew](https://brew.sh/).

```bash
brew install ffmpeg python@3.12 node
git clone <your-repo> spool && cd spool
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm install --prefix frontend
cp .env.example .env
```

Optional: put a Gemini key in `.env` (`GEMINI_API_KEY`). Leave it blank and Spool still cuts, using the local ranker. OpenAI and Anthropic are the same shape — set `LLM_PROVIDER` if you want one of those instead. See `.env.example`. Never commit `.env`.

The first real transcription downloads a Whisper model (the `base` default is a few hundred megabytes) into the Hugging Face cache.

## Run

```bash
./run.sh
```

Open [http://127.0.0.1:8742](http://127.0.0.1:8742).

`./run.sh` creates the virtualenv, installs Python and npm packages if they are missing, copies `.env.example` when you have no `.env`, and starts the API on port 8741 plus the web app on 8742.

### Try it without a video of your own

Click **Cut the sample reel**. That builds a 28-second landscape clip with a moving subject and a built-in transcript, then runs the same cutter. It does not call Whisper or a paid API.

To run that path from the terminal:

```bash
source .venv/bin/activate
python backend/scripts/e2e_sample.py
```

Clips land in `data/e2e/clips/`.

## Tests

```bash
source .venv/bin/activate
cd backend && python -m pytest
```

Unit tests cover silence trimming, timestamp math, highlight JSON parsing, the local ranker, caption generation, crop math, and the MLT export. One end-to-end test generates a short video and checks that the heuristic path writes a captioned 9:16 mp4 plus an MLT project. No API key is required.

## Layout

```
backend/app/transcribe.py    faster-whisper
backend/app/providers.py     Gemini, OpenAI, Anthropic, or the local ranker
backend/app/highlights.py    JSON parsing and the heuristic
backend/app/silence.py       filler words and dead air
backend/app/reframe.py       9:16 crop, face, then motion
backend/app/edit.py          punch-ins and xfade choice
backend/app/captions.py      ASS captions
backend/app/render.py        FFmpeg
backend/app/mlt.py           Kdenlive / Shotcut project
frontend/                    React, Vite, Tailwind
```

## Knobs

| Setting | What it does |
| --- | --- |
| Clips | How many moments to keep (1–8) |
| Shortest / longest | Length window, default 15–45s |
| Captions | Hormozi (caps, yellow word), Pop (coral word), Clean (sentence case) |
| Whisper | `tiny` is the fastest. `base` is the default. `small` is clearer and slower |
| Highlights | Auto uses the first configured key, otherwise the local ranker |
| Picture | 720×1280 is quick. 1080×1920 is sharper |
| Audio & scene hints | Boosts the local ranker with loudness and scene changes. Skipped automatically on very long files |

## Limits

- Face tracking uses OpenCV’s built-in frontal-face detector, then falls back to whatever is moving, then a center crop. Profile shots and crowded frames are the weak cases.
- Jump cuts, punch-ins, and transitions are burned into the mp4. The MLT file is the source media with those cuts on a vertical profile, so you can recut timing in a real editor. It does not redo captions or zooms inside Kdenlive.
- An hour-long file on CPU will spend most of its time in Whisper. `tiny` or `base` with `WHISPER_DEVICE=cpu` is the practical setting on a laptop. There is no GPU requirement.
- Scene detection is skipped past 8 minutes, and the loudness pass past 20 minutes, so a long upload stays responsive.
- Captions need FFmpeg built with libass (the Homebrew and Ubuntu builds are). Fonts ship in `backend/app/assets/fonts/`.
