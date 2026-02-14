"""Quick diagnostic: test VOSK STT directly on saved audio file."""
import os, json, wave, sys

# 1. Check audio file
audio_path = "data/tmp/visitor_e6e23dae/ring_audio.wav"
if not os.path.exists(audio_path):
    print(f"Audio file not found: {audio_path}")
    sys.exit(1)

wf = wave.open(audio_path, "rb")
print(f"Audio file: {audio_path}")
print(f"  Channels: {wf.getnchannels()}")
print(f"  Sample width: {wf.getsampwidth()} bytes")
print(f"  Frame rate: {wf.getframerate()} Hz")
print(f"  Frames: {wf.getnframes()}")
print(f"  Duration: {wf.getnframes() / wf.getframerate():.2f}s")
print(f"  File size: {os.path.getsize(audio_path)} bytes")
wf.close()

# 2. Check VOSK models
print()
for d in ["models/vosk-model-small-en-in-0.4", "models/vosk-model-small-hi-0.22"]:
    exists = "EXISTS" if os.path.isdir(d) else "MISSING"
    print(f"  {d}: {exists}")

# 3. Try VOSK directly
print("\n--- Running VOSK recognition ---")
try:
    import vosk
    vosk.SetLogLevel(0)  # enable VOSK debug logging

    model_path = "models/vosk-model-small-en-in-0.4"
    if not os.path.isdir(model_path):
        print(f"Model not found: {model_path}")
        sys.exit(1)

    model = vosk.Model(model_path)
    wf = wave.open(audio_path, "rb")
    rec = vosk.KaldiRecognizer(model, wf.getframerate())

    print(f"  Recognizer created (rate={wf.getframerate()})")

    chunk_count = 0
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        chunk_count += 1
        accepted = rec.AcceptWaveform(data)
        if accepted:
            result = json.loads(rec.Result())
            print(f"  Partial result (chunk {chunk_count}): {result}")

    final = json.loads(rec.FinalResult())
    print(f"  Final result: {final}")
    wf.close()

except ImportError:
    print("vosk not installed!")
except Exception as e:
    print(f"Error: {e}")
