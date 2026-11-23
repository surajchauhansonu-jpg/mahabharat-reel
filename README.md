# Mahabharat video bot (GitHub -> Telegram)

Topic do -> Hindi script -> scene images -> Hindi voiceover -> animated 9:16 video (bina subtitle) -> Telegram pe MP4.
Sab kuch GitHub Actions me chalta hai, tumhare PC ki zarurat nahi.

## Setup (ek baar, ~10 min)

1. GitHub pe naya repo banao (**Public** rakho to Actions minutes unlimited free; Private me mahine ke ~2000 min free) aur ye saari files upload karo.
2. Telegram: `@BotFather` -> `/newbot` -> token copy karo. Phir apne bot ko ek message bhejo.
   Chat id ke liye `@userinfobot` ko message karo, wo tumhara numeric id bata dega.
3. Gemini key: https://aistudio.google.com/apikey -> Create API key.
4. Repo me **Settings -> Secrets and variables -> Actions -> New repository secret**:
   - `GEMINI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `HF_TOKEN` (optional, image backup ke liye: huggingface.co/settings/tokens, free)
5. **Actions -> Make Video -> Telegram -> Run workflow**. Topic likho (ya khali chhodo) aur Run dabao.
   15-30 min me video Telegram pe aa jayega. Mobile pe GitHub app se bhi Run kar sakte ho.

## Roz apne aap
`.github/workflows/make_video.yml` me `schedule` ki 2 line se `#` hata do.

## Customize
- Music: `assets/music.mp3` daalo.
- Style / voice / model: workflow ke `env` me ye add karo: `STYLE`, `TTS_VOICE` (`hi-IN-SwaraNeural` = female),
  `IMAGE_PROVIDERS` (default `pollinations,huggingface,gemini`), `GEMINI_TEXT_MODEL`.
- Topics: `topics.txt`.

## Dhyan rakho
- Images free AI services se aati hain. Gemini ka image model free tier me band ho sakta hai, isliye default pehle
  Pollinations, phir HuggingFace chalta hai. Quality aur character consistency har video me thodi alag ho sakti hai.
- Mythology ka content: script publish karne se pehle ek baar khud padh lo, AI galti kar sakta hai.
- Telegram bot 50 MB tak ki file bhejta hai, tool khud size chhota kar leta hai.

## v2: animation + audio (kya badla)
- Har image ka depth map (Depth Anything V2, free) nikalta hai -> 3D parallax camera, mid-scene punch-in cut, handheld shake, glow, flicker.
- Audio: cinematic drone + dhol pulse + bells (khud ban jaata hai) ya `assets/music/` ki tumhari music, har cut pe whoosh/boom, voice pe EQ + compression, voice ke time music neeche (ducking).
- Color tint bug fix (pehle video pink/purple ho jata tha).
- Pehli run me depth model (~120 MB) download hota hai, uske baad cache se.

## v3: rigged characters (har scene me wahi chehra)
1. Ek baar: Actions -> **Make Characters (ek baar)** -> names me `Krishna,Arjun,Karna` (ya `all`) -> Run.
   Har character ke 4 candidates banenge, behtareen auto-select hoga aur Telegram pe contact sheet aayegi.
   Dusra pasand ho to dobara run karo, `pick` me `Arjun=2` likho.
2. Characters `characters/` folder me save ho jate hain. Naya character jodna ho to `characters.json` me line add karo.
3. Phir normal **Make Video** chalao: jin scenes me character bolta/khada hai wahan wo rig hoke chalta hai
   (saans, sar hilna, haath, kapde ka hilna, voice ke saath sync), baaki scenes (jung, yuddh, hathiyar) normal image + 3D camera.

## v4: VECTOR PUPPET mode (default) - reference jaisa style
- Characters aur scenes **code se draw** hote hain (Skia): jointed puppets, mukut, kavach, dhoti, mandala-sun, khambhe, baadal, roshni.
- AI image / Cloudflare / HuggingFace ki zarurat nahi. Har scene me character bilkul wahi rehta hai.
- Mooh voice ke saath sync, haath ke ishare, namaste, gussa, udaas, chalna, ladna, tairna (gods).
- Cast `vp_cast.py` me hai (Krishna, Arjun, Karna, Duryodhan, Bhishma, Draupadi, Yudhishthir, Bhima, Shakuni, Ashwatthama, Dronacharya,
  Abhimanyu, Gandhari, Dhritarashtra, Kunti, Barbarik, Ghatotkacha, Sanjay, Vyasa, Brahma, Surya). Naya character = ek entry add karo.
- Purana AI-image mode chahiye to workflow env me `MODE: images`.
