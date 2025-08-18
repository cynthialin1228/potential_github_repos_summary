import os, sys, shutil, subprocess
from datetime import datetime

OUTPUT_DIR = "output"

def _which(cmd):
    return shutil.which(cmd) is not None

def _ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def _convert_with_ffmpeg(src, dst):
    if not _which("ffmpeg"):
        return None
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k", dst],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return dst if os.path.exists(dst) else None
    except Exception:
        return None

def _change_ext(path, new_ext):
    base, _ = os.path.splitext(path)
    return base + new_ext

def generate_tts(text, output_filepath):
    """
    Generate speech audio from `text`.
    Tries gTTS -> pyttsx3 -> OS tools. Returns the final saved file path.
    May change extension if MP3 isn't possible; caller should use the returned path.
    """
    if not text or not text.strip():
        raise ValueError("Text is empty.")

    out_dir = os.path.dirname(output_filepath) or OUTPUT_DIR
    _ensure_dir(out_dir)
    requested_ext = os.path.splitext(output_filepath)[1].lower() or ".mp3"

    # 1) gTTS (saves MP3 directly)
    try:
        from gtts import gTTS  # type: ignore
        mp3_path = output_filepath if requested_ext == ".mp3" else _change_ext(output_filepath, ".mp3")
        tts = gTTS(text)
        tts.save(mp3_path)
        return mp3_path
    except Exception:
        pass

    # 2) pyttsx3 (saves WAV, optional mp3 via ffmpeg)
    try:
        import pyttsx3  # type: ignore
        wav_path = _change_ext(output_filepath, ".wav")
        engine = pyttsx3.init()
        engine.save_to_file(text, wav_path)
        engine.runAndWait()
        if os.path.exists(wav_path) and requested_ext == ".mp3":
            mp3_path = _change_ext(output_filepath, ".mp3")
            out = _convert_with_ffmpeg(wav_path, mp3_path)
            if out:
                try: os.remove(wav_path)
                except: pass
                return mp3_path
        if os.path.exists(wav_path):
            return wav_path
    except Exception:
        pass

    # 3) OS-specific tools
    platform = sys.platform

    # macOS: 'say' -> AIFF; convert via afconvert/ffmpeg if possible
    if platform == "darwin" and _which("say"):
        aiff_path = _change_ext(output_filepath, ".aiff")
        try:
            subprocess.run(
                ["say", "-o", aiff_path, text],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if requested_ext == ".mp3":
                mp3_path = _change_ext(output_filepath, ".mp3")
                # prefer afconvert -> m4a if ffmpeg unavailable
                if _which("afconvert"):
                    m4a_path = _change_ext(output_filepath, ".m4a")
                    try:
                        subprocess.run(
                            ["afconvert", "-f", "m4af", "-d", "aac", aiff_path, m4a_path],
                            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
                        try: os.remove(aiff_path)
                        except: pass
                        return m4a_path
                    except Exception:
                        pass
                out = _convert_with_ffmpeg(aiff_path, mp3_path)
                if out:
                    try: os.remove(aiff_path)
                    except: pass
                    return mp3_path
            return aiff_path
        except Exception:
            pass

    # Linux: espeak-ng/espeak -> WAV; convert via ffmpeg if possible
    if platform.startswith("linux") and (_which("espeak-ng") or _which("espeak")):
        wav_path = _change_ext(output_filepath, ".wav")
        try:
            cmd = ["espeak-ng", "-w", wav_path, text] if _which("espeak-ng") else ["espeak", "-w", wav_path, text]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if requested_ext == ".mp3":
                mp3_path = _change_ext(output_filepath, ".mp3")
                out = _convert_with_ffmpeg(wav_path, mp3_path)
                if out:
                    try: os.remove(wav_path)
                    except: pass
                    return mp3_path
            return wav_path
        except Exception:
            pass

    # Windows fallback: try PowerShell SAPI to WAV
    if platform.startswith("win"):
        wav_path = _change_ext(output_filepath, ".wav")
        ps_script = f"""
Add-Type -AssemblyName System.speech
$spk = New-Object System.Speech.Synthesis.SpeechSynthesizer
$spk.Rate = 0
$out = '{wav_path.replace("'", "''")}'
$spk.SetOutputToWaveFile($out)
$spk.Speak('{text.replace("'", "''")}')
$spk.Dispose()
"""
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if os.path.exists(wav_path) and requested_ext == ".mp3":
                mp3_path = _change_ext(output_filepath, ".mp3")
                out = _convert_with_ffmpeg(wav_path, mp3_path)
                if out:
                    try: os.remove(wav_path)
                    except: pass
                    return mp3_path
            if os.path.exists(wav_path):
                return wav_path
        except Exception:
            pass

    raise RuntimeError(
        "No TTS backend available. Install one of: "
        "gTTS (`pip install gTTS`), pyttsx3 (`pip install pyttsx3`), "
        "or ensure OS TTS tools are available (macOS `say`, Linux `espeak-ng`/`espeak`)."
    )

def generate_tts_from_text(text, filename=None):
    # os.makedirs(OUTPUT_DIR, exist_ok=True)
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"sample_tts_{timestamp}.mp3"
    output_filepath = filename
    final_path = generate_tts(text, output_filepath)
    return final_path

if __name__ == "__main__":
    # sample_text = "This is a sample text to demonstrate text-to-speech conversion."
    sample_text = ""    
    with open("/Users/cynthia/Documents/yt_github_repo_news/output/google-gemini_gemini-cli_20250818_001114/summary.txt", "r", encoding="utf-8") as f:
        sample_text = f.read()
    # output_file in the same directory /Users/cynthia/Documents/yt_github_repo_news/output/google-gemini_gemini-cli.... /voice.mp3
    output_filename = "/Users/cynthia/Documents/yt_github_repo_news/output/google-gemini_gemini-cli_20250818_001114/voice.mp3"
    saved_path = generate_tts_from_text(sample_text, output_filename)
    print(f"TTS audio saved to {saved_path}")
