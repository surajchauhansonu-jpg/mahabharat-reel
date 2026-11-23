#!/usr/bin/env python3
"""
Topic -> Hindi script -> scene images -> Hindi voiceover -> animated 9:16 video -> Telegram.
Runs fully inside GitHub Actions. No subtitles (by design).

Env vars (set as GitHub Secrets / workflow inputs):
  GEMINI_API_KEY      required (script writing, free tier text model)
  TELEGRAM_BOT_TOKEN  required (to receive the video)
  TELEGRAM_CHAT_ID    required
  HF_TOKEN            optional (fallback image provider)
  TOPIC               optional (else picked from topics.txt)
  SCENES              optional, default 14
  DRY_RUN=1           test the video assembly without any network/AI
"""
import asyncio
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

import cv2
import numpy as np
import requests

import animate
import audiofx
import rig
import vp_cast
import vp_world
from PIL import Image, ImageDraw, ImageFilter

W, H, FPS = 720, 1280, 30
OUT = Path("output")
WORK = Path("work")

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
SCRIPT_PROVIDERS = [p.strip() for p in os.getenv("SCRIPT_PROVIDERS", "github,gemini").split(",") if p.strip()]
GITHUB_MODELS = [m.strip() for m in os.getenv(
    "GITHUB_MODELS", "openai/gpt-4.1,openai/gpt-4o,openai/gpt-4o-mini,meta/Llama-3.3-70B-Instruct").split(",") if m.strip()]
TTS_PROVIDERS = [p.strip() for p in os.getenv("TTS_PROVIDERS", "edge,piper").split(",") if p.strip()]
PIPER_VOICE = os.getenv("PIPER_VOICE", "pratham")  # pratham / rohan (male), priyamvada (female)
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
IMAGE_PROVIDERS = [p.strip() for p in os.getenv("IMAGE_PROVIDERS", "cloudflare,pollinations").split(",") if p.strip()]
HF_MODEL_URL = os.getenv("HF_MODEL_URL", "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell")
VOICE = os.getenv("TTS_VOICE", "hi-IN-MadhurNeural")
TTS_RATE = os.getenv("TTS_RATE", "-4%")
TTS_PITCH = os.getenv("TTS_PITCH", "")  # thodi bhari, dramatic awaaz
MODE = os.getenv("MODE", "vector")   # vector = code-drawn puppets (default) | images = AI images
CACHE = Path("models_cache")
CHAR_DIR = Path("characters")
POS = {"left": (0.30, 0.93), "center": (0.50, 0.93), "right": (0.70, 0.93)}
_ACTORS = {}


def known_characters():
    return sorted(p.stem for p in CHAR_DIR.glob("*.png")) if CHAR_DIR.exists() else []


def char_descriptions():
    f = Path("characters.json")
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def get_actor(name, height_px):
    key = (name.lower(), height_px)
    if key not in _ACTORS:
        match = [p for p in CHAR_DIR.glob("*.png") if p.stem.lower() == name.lower()]
        if not match:
            return None
        _ACTORS[key] = rig.Actor(match[0], height_px)
    return _ACTORS[key]
STYLE = os.getenv(
    "STYLE",
    "flat 2D vector illustration, Indian mythology Mahabharat, cutout puppet style characters, "
    "thick dark outlines, rich warm colours, cinematic dramatic lighting, soft glow, "
    "vertical 9:16 composition, single clear focal point, no text, no letters, no watermark",
)


def log(*a):
    print(*a, flush=True)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        log("CMD FAILED:", " ".join(map(str, cmd))[:300])
        log(r.stderr[-1500:])
        raise RuntimeError("command failed")
    return r.stdout


# --------------------------------------------------------------------------- script
def parse_json(txt):
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    i, j = txt.find("{"), txt.rfind("}")
    if i != -1 and j != -1:
        txt = txt[i:j + 1]
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return json.loads(re.sub(r",(\s*[}\]])", r"\1", txt))  # trailing commas


def github_text(prompt):
    """Free LLM via GitHub Models (uses the workflow's own GITHUB_TOKEN, no extra key)."""
    tok = os.environ.get("GITHUB_TOKEN")
    if not tok:
        raise RuntimeError("GITHUB_TOKEN missing")
    url = "https://models.github.ai/inference/chat/completions"
    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
               "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    for model in GITHUB_MODELS:
        body = {"model": model, "temperature": 0.9, "max_tokens": 3800,
                "messages": [{"role": "system", "content": "You output only one valid JSON object, nothing else."},
                             {"role": "user", "content": prompt}]}
        for attempt in range(2):
            try:
                r = requests.post(url, headers=headers, json=body, timeout=150)
            except requests.exceptions.RequestException as e:
                log(f"  github/{model}: network error: {str(e)[:150]}")
                time.sleep(5)
                continue
            if r.status_code in (500, 502, 503):
                log(f"  github/{model}: HTTP {r.status_code}")
                time.sleep(8 * (attempt + 1))
                continue
            if r.status_code != 200:
                log(f"  github/{model}: HTTP {r.status_code} {r.text[:300]}")
                break  # 401/403 (permission), 404 (model), 429 (limit) -> next model
            try:
                data = parse_json(r.json()["choices"][0]["message"]["content"])
                log(f"  script ready via github/{model}")
                return data
            except Exception as e:  # noqa: BLE001
                log(f"  github/{model}: bad JSON ({str(e)[:100]}), retrying")
    raise RuntimeError("GitHub Models failed")


def gemini_text(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing")
    models = [TEXT_MODEL, "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-latest"]
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
    }
    for model in dict.fromkeys(models):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        for attempt in range(2):
            try:
                r = requests.post(url, json=body, timeout=150)
            except requests.exceptions.RequestException as e:
                log(f"  {model}: network/timeout error: {str(e)[:150]}")
                time.sleep(5)
                continue
            if r.status_code == 429:
                log(f"  {model}: HTTP 429 {r.text[:200]}")
                break
            if r.status_code in (500, 503):
                log(f"  {model}: HTTP {r.status_code} {r.text[:200]}")
                time.sleep(8 * (attempt + 1))
                continue
            if r.status_code != 200:
                log(f"  {model}: HTTP {r.status_code} {r.text[:300]}")
                break
            try:
                data = parse_json(r.json()["candidates"][0]["content"]["parts"][0]["text"])
                log(f"  script ready via {model}")
                return data
            except Exception as e:  # noqa: BLE001
                log(f"  {model}: bad response ({str(e)[:100]}), retrying")
    raise RuntimeError("Gemini text failed on all models")


def llm_json(prompt):
    fns = {"github": github_text, "gemini": gemini_text}
    last = None
    for name in SCRIPT_PROVIDERS:
        try:
            return fns[name](prompt)
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"  script provider '{name}' failed: {str(e)[:150]}")
    raise RuntimeError(f"all script providers failed: {last}")


def write_script(topic, n, rigged=()):
    rig_rule = (
        f"- RIGGED CHARACTERS available (exact names): {', '.join(rigged)}. For a scene where one or two of them "
        "stand and speak/react, set mode='rig', give 'background_prompt' (English, the EMPTY environment only: "
        "no people), and 'actors': [{name, pos: left|center|right, action: talk|idle|angry|shock|walk}]. "
        "Use at least 60% rig scenes when possible. For landscapes, battles, objects, silhouettes, or characters "
        "not in the list use mode='plate' (normal image_prompt).\n"
    ) if rigged else ""
    prompt = (
        "You are a scriptwriter for viral Hindi short-form animated storytelling videos on Indian mythology "
        "(Mahabharat, Ramayan, Puranas).\n"
        f"Topic: {topic}\n"
        f"Write exactly {n} scenes. Rules:\n"
        "- narration: simple conversational Hindi in Devanagari, ONE or TWO short sentences per scene "
        "(max 14 words), dramatic storytelling tone, short punchy sentences. Scene 1 must be a strong hook "
        "(a question or a shocking secret). The last scene is a cliffhanger or 'Part 2' tease.\n"
        "- Stay with well-known accounts from the texts. Do not invent facts. Respectful tone; "
        "nothing insulting to any religion, caste or community.\n"
        "- characters: an object mapping each recurring character name (English) to ONE fixed English visual "
        "description (skin tone, clothes colours, crown/ornaments, beard, age). Keep it identical for all scenes.\n"
        "- image_prompt: English. Start with the SHOT TYPE, then the setting, action, mood, lighting. "
        "Refer to characters by the exact names used in 'characters'. No text in the image. "
        "VARY the shots: wide establishing shot, medium shot, low-angle hero shot, silhouette, "
        "back view, over-the-shoulder, hands or object close-up (weapon, dice, bow, lamp, fire), "
        "landscape/sky/battlefield. Use a face close-up in AT MOST 3 scenes. "
        "Prefer shots where the face is small or hidden, so the character stays consistent.\n"
        "- scene.characters: list of character names appearing in that scene.\n"
        + rig_rule +
        "- scene.energy: 1 = calm, 2 = tense, 3 = action/shock (controls camera shake and sound).\n"
        'Return ONLY JSON: {"title":"(Hindi)","description":"(Hindi, 2 lines)","hashtags":["#..."],'
        '"characters":{"Name":"visual description"},'
        '"scenes":[{"mode":"plate|rig","narration":"...","image_prompt":"...","background_prompt":"(rig only)",'
        '"actors":[{"name":"Arjun","pos":"left","action":"talk"}],"characters":["Name"],"energy":2}]}'
    )
    data = llm_json(prompt)
    assert data.get("scenes"), "empty script"
    return data


# --------------------------------------------------------------------------- images
def _valid_image(b):
    import io

    Image.open(io.BytesIO(b)).verify()
    return b


def img_pollinations(prompt, seed):
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:1400])
    r = requests.get(url, params=dict(width=W, height=H, seed=seed, nologo="true", model="flux"), timeout=180)
    r.raise_for_status()
    return _valid_image(r.content)


def img_huggingface(prompt, seed):
    tok = os.environ["HF_TOKEN"]
    r = requests.post(
        HF_MODEL_URL,
        headers={"Authorization": f"Bearer {tok}"},
        json={"inputs": prompt, "parameters": {"width": 720, "height": 1280, "seed": seed}},
        timeout=180,
    )
    r.raise_for_status()
    return _valid_image(r.content)


def img_gemini(prompt, seed):
    import base64

    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": prompt + " Vertical 9:16 image."}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    r = requests.post(url, json=body, timeout=180)
    r.raise_for_status()
    for p in r.json()["candidates"][0]["content"]["parts"]:
        d = p.get("inlineData") or p.get("inline_data")
        if d:
            return _valid_image(base64.b64decode(d["data"]))
    raise RuntimeError("no image in Gemini response")


def img_cloudflare(prompt, seed):
    import base64

    acc, tok = os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    r = requests.post(url, headers={"Authorization": f"Bearer {tok}"},
                      json={"prompt": prompt[:2000], "steps": 6}, timeout=180)
    if r.status_code != 200:
        raise requests.HTTPError(f"{r.status_code} {r.text[:250]}", response=r)
    if r.headers.get("content-type", "").startswith("image/"):
        return _valid_image(r.content)
    return _valid_image(base64.b64decode(r.json()["result"]["image"]))


PROVIDER_FN = {"cloudflare": img_cloudflare, "pollinations": img_pollinations, "huggingface": img_huggingface, "gemini": img_gemini}


def make_image(prompt, idx, path):
    seed = random.randint(1, 10**6)
    last = None
    for name in IMAGE_PROVIDERS:
        if name == "huggingface" and not os.getenv("HF_TOKEN"):
            continue
        if name == "cloudflare" and not (os.getenv("CF_ACCOUNT_ID") and os.getenv("CF_API_TOKEN")):
            log("  cloudflare keys missing, skipping")
            continue
        for attempt in range(3):
            try:
                data = PROVIDER_FN[name](prompt, seed + attempt)
                save_cover(data, path)
                log(f"  image {idx}: {name} ok")
                return
            except Exception as e:  # noqa: BLE001
                last = e
                log(f"  image {idx}: {name} attempt {attempt + 1} failed: {str(e)[:250]}")
                code = getattr(getattr(e, "response", None), "status_code", None)
                if code in (400, 401, 402, 403, 404, 410, 429):
                    break  # retry ka fayda nahi (quota / galat key / band endpoint)
                time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"all image providers failed: {last}")


def save_cover(data, path, scale=2):
    """Crop to 9:16 and upscale (zoompan looks smoother on a larger source)."""
    import io

    im = Image.open(io.BytesIO(data)).convert("RGB")
    tw, th = W * scale, H * scale
    r = max(tw / im.width, th / im.height)
    im = im.resize((math.ceil(im.width * r), math.ceil(im.height * r)), Image.LANCZOS)
    left, top = (im.width - tw) // 2, (im.height - th) // 2
    im.crop((left, top, left + tw, top + th)).save(path, quality=95)


def make_dummy_character(path):
    from PIL import ImageDraw

    im = Image.new("RGBA", (400, 900), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([140, 20, 260, 160], fill=(230, 180, 120, 255))
    d.rectangle([180, 150, 220, 200], fill=(230, 180, 120, 255))
    d.rectangle([130, 195, 270, 480], fill=(40, 90, 200, 255))
    d.rectangle([75, 200, 125, 470], fill=(230, 180, 120, 255))
    d.rectangle([275, 200, 325, 470], fill=(230, 180, 120, 255))
    d.polygon([(130, 470), (270, 470), (300, 880), (100, 880)], fill=(250, 190, 40, 255))
    im.save(path)


def placeholder_image(idx, path):
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        c = int(40 + 160 * y / H)
        d.line([(0, y), (W, y)], fill=((c + idx * 25) % 255, 60, 200 - c // 2))
    d.ellipse([W // 2 - 120, H // 2 - 120, W // 2 + 120, H // 2 + 120], fill=(255, 200, 60))
    buf = Path(path).with_suffix(".tmp.png")
    im.save(buf)
    save_cover(buf.read_bytes(), path)
    buf.unlink()


# --------------------------------------------------------------------------- voice
def clean_text(t):
    t = re.sub(r"[\*_#\"“”‘’`~|<>\[\]{}]", "", t)
    t = t.replace("…", "...").replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


async def _edge(text, path, voice, rate, pitch):
    import edge_tts

    kw = {}
    if rate:
        kw["rate"] = rate
    if pitch:
        kw["pitch"] = pitch
    await edge_tts.Communicate(text, voice, **kw).save(str(path))


def tts_edge(text, path):
    tries = [(VOICE, TTS_RATE, TTS_PITCH or None), (VOICE, None, None), (VOICE, TTS_RATE, None), (VOICE, None, None),
             ("hi-IN-SwaraNeural", None, None), (VOICE, None, None), (VOICE, None, None)]
    for n, (voice, rate, pitch) in enumerate(tries, 1):
        try:
            asyncio.run(_edge(text, path, voice, rate, pitch))
            if Path(path).exists() and Path(path).stat().st_size > 1000:
                return
        except Exception as e:  # noqa: BLE001
            log(f"  edge-tts try {n} ({voice}) failed: {str(e)[:110]}")
        time.sleep(2 * n)
    raise RuntimeError("edge-tts failed")


def tts_piper(text, path):
    """Offline Hindi voice (Piper). Model is downloaded once from Hugging Face."""
    import wave

    from piper import PiperVoice

    mdir = CACHE / "piper"
    mdir.mkdir(parents=True, exist_ok=True)
    name = f"hi_IN-{PIPER_VOICE}-medium"
    base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/hi/hi_IN/{PIPER_VOICE}/medium/{name}"
    for ext in (".onnx", ".onnx.json"):
        f = mdir / (name + ext)
        if not f.exists():
            log(f"  downloading piper voice {name}{ext}")
            r = requests.get(base + ext, timeout=300)
            r.raise_for_status()
            f.write_bytes(r.content)
    voice = PiperVoice.load(str(mdir / (name + ".onnx")), config_path=str(mdir / (name + ".onnx.json")))
    wav = Path(path).with_suffix(".wav")
    with wave.open(str(wav), "wb") as wf:
        if hasattr(voice, "synthesize_wav"):
            voice.synthesize_wav(text, wf)
        else:
            voice.synthesize(text, wf)
    run(["ffmpeg", "-y", "-i", str(wav), "-q:a", "4", str(path)])
    wav.unlink()


VOICE_LOG = []


def make_voice(text, path):
    text = clean_text(text)
    fns = {"edge": tts_edge, "piper": tts_piper}
    last = None
    for name in TTS_PROVIDERS:
        try:
            fns[name](text, path)
            log(f"  voice: {name} ok")
            VOICE_LOG.append(name)
            return
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"  voice provider '{name}' failed: {str(e)[:150]}")
    raise RuntimeError(f"TTS failed: {last}")


def silent_voice(path, secs=3.0):
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={secs}", "-q:a", "5", str(path)])


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).strip())


# --------------------------------------------------------------------------- video
def build_clip(img, audio, idx, out, energy=2, use_model=True, actors=None):
    """Animated 2.5D clip + voice. Returns (duration, internal_cut_time_or_None)."""
    pad = 0.3
    dur = max(duration(audio) + pad, 3.0)
    src = cv2.imread(str(img))
    depth = animate.get_depth(src, cache_dir=CACHE, use_model=use_model)
    vid = WORK / f"s{idx}_v.mp4"
    env = animate.voice_env(audio, int(math.ceil(dur * FPS)) + 2)
    cut = animate.render_scene(src, depth, dur, idx, vid, energy=energy, actors=actors, env=env)
    run([
        "ffmpeg", "-y", "-i", str(vid), "-i", str(audio),
        "-filter_complex", f"[1:a]apad=pad_dur={pad + 3},aresample=44100,aformat=channel_layouts=stereo[a]",
        "-map", "0:v", "-map", "[a]", "-t", f"{dur:.3f}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(out),
    ])
    return dur, cut


def make_particles(path, seconds=20, n=90):
    """Seamless looping golden dust, blended over the final video."""
    rng = np.random.default_rng(7)
    x0, y0 = rng.uniform(0, W, n), rng.uniform(0, H, n)
    k = rng.integers(1, 3, n)  # integer laps -> seamless loop
    m1, m2 = rng.integers(1, 4, n), rng.integers(3, 6, n)
    size, phase = rng.uniform(1.5, 4.2, n), rng.uniform(0, 6.28, n)
    drift = rng.uniform(6, 22, n)
    p = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast", str(path)],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    for f in range(seconds * FPS):
        t = f / FPS
        img = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(img)
        for i in range(n):
            y = (y0[i] - H * k[i] * t / seconds) % H
            x = (x0[i] + math.sin(2 * math.pi * m1[i] * t / seconds + phase[i]) * drift[i]) % W
            tw = 0.5 + 0.5 * math.sin(2 * math.pi * m2[i] * t / seconds + phase[i])
            c = int(110 + 145 * tw)
            r = size[i]
            d.ellipse([x - r, y - r, x + r, y + r], fill=(c, int(c * 0.78), int(c * 0.4)))
        p.stdin.write(img.filter(ImageFilter.GaussianBlur(1.1)).tobytes())
    p.stdin.close()
    p.wait()


def assemble(clips, total, out, scene_starts, cut_times, energies=None, overlay=True):
    lst = WORK / "clips.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    joined = WORK / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])

    bed, sfx = audiofx.build_audio_assets(total, scene_starts, cut_times, WORK, energies=energies)
    if overlay:
        particles = WORK / "particles.mp4"
        make_particles(particles)
        inputs = ["-i", str(joined), "-stream_loop", "-1", "-i", str(particles), "-i", str(bed), "-i", str(sfx)]
        bi, si = 2, 3
        fv = ("[0:v]format=gbrp[a];[1:v]format=gbrp[b];"
              "[a][b]blend=all_mode=screen:all_opacity=0.55,format=yuv420p,vignette=PI/6,"
              f"eq=contrast=1.05:saturation=1.08,fade=t=in:st=0:d=0.4,fade=t=out:st={total - 0.8:.2f}:d=0.8[v];")
    else:
        inputs = ["-i", str(joined), "-i", str(bed), "-i", str(sfx)]
        bi, si = 1, 2
        fv = f"[0:v]fade=t=in:st=0:d=0.3,fade=t=out:st={total - 0.8:.2f}:d=0.8[v];"
    fa = ("[0:a]highpass=f=70,equalizer=f=120:t=q:w=1:g=2,equalizer=f=3500:t=q:w=1:g=1.5,"
          "acompressor=threshold=0.1:ratio=2.5:attack=8:release=160:makeup=2,asplit=2[vo][sc];"
          f"[{bi}:a]volume=0.5[bed];[bed][sc]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=450[duck];"
          f"[{si}:a]volume=0.6[fx];"
          "[vo][duck][fx]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.95,"
          f"loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=out:st={total - 1.0:.2f}:d=1.0[a]")
    run(["ffmpeg", "-y", *inputs,
         "-filter_complex", fv + fa, "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", str(out)])
    # Telegram bot upload limit is 50 MB
    crf = 23
    while out.stat().st_size > 48 * 1024 * 1024 and crf < 36:
        crf += 4
        small = out.with_suffix(".small.mp4")
        run(["ffmpeg", "-y", "-i", str(out), "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(small)])
        small.replace(out)


# --------------------------------------------------------------------------- telegram
def tg_api(method, **kw):
    tok = os.environ["TELEGRAM_BOT_TOKEN"]
    return requests.post(f"https://api.telegram.org/bot{tok}/{method}", timeout=600, **kw)


def send_telegram(video, meta):
    chat = os.environ["TELEGRAM_CHAT_ID"]
    caption = f"{meta.get('title', '')}\n\n{meta.get('description', '')}\n\n{' '.join(meta.get('hashtags', []))}"[:1000]
    with open(video, "rb") as f:
        r = tg_api("sendVideo", data={"chat_id": chat, "caption": caption, "supports_streaming": "true",
                                      "width": W, "height": H}, files={"video": f})
    log("telegram:", r.status_code, r.text[:200])
    r.raise_for_status()
    narr = "\n".join(f"{i + 1}. {s['narration']}" for i, s in enumerate(meta["scenes"]))
    rep = meta.get("voice_report")
    head = (f"Voice: {rep}\n\n" if rep else "")
    tg_api("sendMessage", data={"chat_id": chat, "text": (head + "Script:\n" + narr)[:4000]})


# --------------------------------------------------------------------------- main
GENERIC_ROLES = "Rishi (any sage), Raja (any king), Rani (any queen), Sainik (any soldier), Balak (any child)"
BACKDROP_HINT = ("sunrise_field (open land, morning), night_sky (night, stars), palace_hall (court/palace), battlefield, "
                 "forest, temple/ashram, cosmic (heaven, gods, creation), sky_clouds (sky, flight), fire (yagya, burning, "
                 "rage), river (river, lake, water)")


def write_script_vector(topic, n, names):
    named = ", ".join(names)
    # ---- step 1: the real story, as ordered beats --------------------------------------------------
    p1 = (
        "You are an expert on the Mahabharat, Ramayan and Puranas. "
        f"Topic of a short video: {topic}\n"
        f"Write the story as exactly {n} ordered story beats, as told in the traditional texts, from the hook to a "
        "cliffhanger. STRICT: only well-known events, never invent facts; if unsure of a detail leave it out. "
        "Each beat: 'event' (one concrete sentence in English: who does what to whom), 'who' (ONLY the characters who "
        f"are physically present in that moment, max 3; use these exact names when they fit: {named}; if the real "
        f"character is not in the list use a generic role: {GENERIC_ROLES}), 'place' (where it happens), "
        "'emotion' (calm/tense/shock/sad/anger/joy/awe).\n"
        'Return ONLY JSON: {"title":"(Hindi)","description":"(Hindi, 2 lines)","hashtags":["#..."],'
        '"beats":[{"event":"...","who":["Karna"],"place":"...","emotion":"tense"}]}'
    )
    outline = llm_json(p1)
    beats = outline.get("beats") or []
    assert beats, "no story beats"

    # ---- step 2: one scene per beat ----------------------------------------------------------------
    p2 = (
        "You direct a flat-vector puppet-theatre video (Hindi voice-over). Convert EVERY story beat below into exactly one "
        "scene, in the same order, nothing added, nothing skipped.\n"
        f"Beats: {json.dumps(beats, ensure_ascii=False)}\n"
        "Rules:\n"
        "- narration: simple conversational Hindi in Devanagari, 1-2 short sentences (max 14 words) that say exactly what "
        "the beat's event is. Beat 1 = strong hook. Last = cliffhanger / 'Part 2'. Respectful, nothing offensive.\n"
        f"- actors[].who = exactly the beat's 'who' (names from: {named}). Never add or swap in another famous character. "
        "No actors only for pure scenery/symbolic beats.\n"
        "- actors[].at: far_left|left|center|right|far_right; face: left|right (toward the other actor). "
        "actors[].action: talk|listen|idle|namaste|bow|pray|point|raise|angry|sad|shock|walk|fight|float|laugh "
        "(talk only for a speaking character; match the beat's emotion). prop (optional): bow|mace|sword|staff|flute|dice|spear.\n"
        "- speaker: index of the actor who speaks or is the focus.\n"
        f"- backdrop must match the beat's place: {BACKDROP_HINT}. palette: sunrise|day|dusk|night|war|mystic|forest|palace. "
        "halo: true only for divine/dramatic moments. particles: dust|embers|petals|stars|none.\n"
        "- energy: 1 calm, 2 tense, 3 ONLY for a real shock/battle/curse moment (use rarely).\n"
        'Return ONLY JSON: {"scenes":[{"narration":"...","backdrop":"palace_hall","palette":"palace","halo":false,'
        '"particles":"dust","energy":2,"speaker":0,"actors":[{"who":"Karna","at":"left","face":"right","action":"idle","prop":"none"}]}]}'
    )
    data = llm_json(p2)
    assert data.get("scenes"), "empty script"

    # ---- step 3: check scenes against the story and fix mismatches --------------------------------
    try:
        p3 = (
            "Quality check for a mythology video. Compare each scene with its story beat (same index). Fix ONLY real "
            "mismatches: wrong or extra characters (actors must equal the beat's 'who'), wrong place/backdrop, wrong "
            "emotion/action, narration that states a wrong or invented fact. Keep the same number of scenes and the same "
            "JSON format. Return ONLY the full corrected JSON {\"scenes\": [...]}.\n"
            f"Beats: {json.dumps(beats, ensure_ascii=False)}\nScenes: {json.dumps(data['scenes'], ensure_ascii=False)}"
        )
        fixed = llm_json(p3)
        if fixed.get("scenes") and len(fixed["scenes"]) == len(data["scenes"]):
            data = fixed
            log("  script: checked and corrected")
    except Exception as e:  # noqa: BLE001
        log(f"  script check skipped: {str(e)[:100]}")
    data["title"] = outline.get("title", "")
    data["description"] = outline.get("description", "")
    data["hashtags"] = outline.get("hashtags", [])
    return data


def build_clip_vector(audio, idx, out, scene, energy, cast):
    pad = 0.3
    dur = max(duration(audio) + pad, 3.0)
    vid = WORK / f"s{idx}_v.mp4"
    env = animate.voice_env(audio, int(math.ceil(dur * FPS)) + 2)
    cut = vp_world.render_scene(scene, dur, env, vid, idx, cast, energy=energy)
    run([
        "ffmpeg", "-y", "-i", str(vid), "-i", str(audio),
        "-filter_complex", f"[1:a]apad=pad_dur={pad + 3},aresample=44100,aformat=channel_layouts=stereo[a]",
        "-map", "0:v", "-map", "[a]", "-t", f"{dur:.3f}",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(out),
    ])
    return dur, cut


def main_vector():
    dry = os.getenv("DRY_RUN") == "1"
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    cast = vp_cast.build_cast()
    if dry:
        meta = {"title": "Test", "description": "dry run", "hashtags": ["#test"], "scenes": [
            {"narration": "a", "backdrop": "sunrise_field", "halo": True, "actors": [{"who": "Karna", "at": "center", "action": "namaste"}]},
            {"narration": "b", "backdrop": "palace_hall", "actors": [{"who": "Karna", "at": "left", "action": "talk"},
                                                                     {"who": "Kunti", "at": "right", "action": "listen"}], "energy": 3},
            {"narration": "c", "backdrop": "night_sky", "halo": True, "particles": "stars",
             "actors": [{"who": "Brahma", "at": "center", "action": "float"}]}]}
    else:
        topic = pick_topic()
        n = int(os.getenv("SCENES", "20"))
        log(f"Topic: {topic} | scenes: {n} | mode: vector")
        meta = write_script_vector(topic, n, list(cast))
    (OUT / "script.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    clips, total, starts, cuts, energies = [], 0.0, [], [], []
    for i, raw in enumerate(meta["scenes"]):
        log(f"Scene {i + 1}/{len(meta['scenes'])}")
        sc = vp_world.clean_scene(raw, cast)
        aud, clip = WORK / f"s{i}.mp3", WORK / f"s{i}.mp4"
        if dry:
            silent_voice(aud, 3.5 + (i % 2))
        else:
            make_voice(raw["narration"], aud)
            time.sleep(1)
        energy = int(raw.get("energy", 2) or 2)
        energies.append(energy)
        starts.append(total)
        dur, cut = build_clip_vector(aud, i, clip, sc, energy, cast)
        if cut:
            cuts.append(total + cut)
        total += dur
        clips.append(clip)

    final = OUT / "final.mp4"
    assemble(clips, total, final, starts, [], energies, overlay=False)   # no per-cut sound effects
    if VOICE_LOG:
        meta['voice_report'] = ', '.join(f'{k} x{VOICE_LOG.count(k)}' for k in sorted(set(VOICE_LOG))) + ('  (piper = robotic backup)' if 'piper' in VOICE_LOG else '')
    log(f"Done: {final} ({final.stat().st_size / 1e6:.1f} MB, {total:.0f}s)")
    if not dry:
        send_telegram(final, meta)


def pick_topic():
    t = os.getenv("TOPIC", "").strip()
    if t:
        return t
    f = Path("topics.txt")
    lines = [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return lines[date.today().toordinal() % len(lines)]


def main():
    if MODE == "vector":
        return main_vector()
    dry = os.getenv("DRY_RUN") == "1"
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)

    if dry:
        meta = {"title": "Test", "description": "dry run", "hashtags": ["#test"], "characters": {},
                "scenes": [{"narration": f"scene {i}", "image_prompt": "x", "characters": []} for i in range(1, 5)]}
    else:
        topic = pick_topic()
        n = int(os.getenv("SCENES", "22"))
        log(f"Topic: {topic} | scenes: {n}")
        meta = write_script(topic, n, known_characters())
    (OUT / "script.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    clips, total = [], 0.0
    scene_starts, cut_times = [], []
    chars = {**meta.get("characters", {}), **char_descriptions()}  # fixed descriptions win -> same look everywhere
    energies = []
    if dry:
        CHAR_DIR.mkdir(exist_ok=True)
        make_dummy_character(CHAR_DIR / "Testman.png")
    for i, sc in enumerate(meta["scenes"]):
        log(f"Scene {i + 1}/{len(meta['scenes'])}")
        img, aud, clip = WORK / f"s{i}.jpg", WORK / f"s{i}.mp3", WORK / f"s{i}.mp4"
        if dry and i == 1:
            sc.update(mode="rig", actors=[{"name": "Testman", "pos": "left", "action": "talk"},
                                          {"name": "Testman", "pos": "right", "action": "angry"}])

        # ---- rigged characters (same face every time) --------------------------------------------
        actors = []
        if sc.get("mode") == "rig":
            acts = (sc.get("actors") or [])[:2]
            hpx = int((0.56 if len(acts) > 1 else 0.64) * H)
            for k, a_ in enumerate(acts):
                ac = get_actor(str(a_.get("name", "")), hpx)
                if ac is None:
                    continue
                pos = a_.get("pos", "center") if len(acts) == 1 else ("left", "right")[k]
                actors.append({"actor": ac, "pos": POS.get(pos, POS["center"]), "flip": pos == "right",
                               "action": a_.get("action", "talk"), "seed": k + i})
            if len(actors) != len(acts):
                actors = []  # a name had no rig -> fall back to a normal plate scene
        rigged = bool(actors)

        if dry:
            placeholder_image(i, img)
            silent_voice(aud, 4.0 + (i % 2))
        else:
            if rigged:
                bg = sc.get("background_prompt") or sc.get("image_prompt", "")
                prompt = f"{bg}. Empty environment, no people, no characters, no figures. Style: {STYLE}"
            else:
                who = "; ".join(f"{c}: {chars[c]}" for c in sc.get("characters", []) if c in chars)
                prompt = f"{sc['image_prompt']}. Characters: {who}. Style: {STYLE}"
            try:
                make_image(prompt, i + 1, img)
            except Exception as e:  # noqa: BLE001
                prev = WORK / f"s{i - 1}.jpg"
                if i > 0 and prev.exists():
                    log(f"  scene {i + 1}: image fail, pichli scene ki image reuse kar raha hoon")
                    img.write_bytes(prev.read_bytes())
                else:
                    raise
            make_voice(sc["narration"], aud)
            time.sleep(2)
        energy = int(sc.get("energy", 2) or 2)
        energies.append(energy)
        scene_starts.append(total)
        dur, cut = build_clip(img, aud, i, clip, energy=energy, use_model=not dry, actors=actors or None)
        if cut:
            cut_times.append(total + cut)
        total += dur
        clips.append(clip)

    final = OUT / "final.mp4"
    assemble(clips, total, final, scene_starts, cut_times, energies)
    log(f"Done: {final} ({final.stat().st_size / 1e6:.1f} MB, {total:.0f}s)")

    if dry:
        return
    send_telegram(final, meta)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        log("ERROR:", e)
        sys.exit(1)
