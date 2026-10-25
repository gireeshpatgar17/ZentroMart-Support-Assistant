"""Batch-process a folder of voice turns using Gnani STT and TTS only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from src.agent import answer

SUPPORTED_AUDIO = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
UINT32_MAX = 0xFFFFFFFF


def normalize_wav_header(path: Path) -> None:
    """Fix Gnani WAV size sentinels to match the actual RIFF and data lengths."""
    file_size = path.stat().st_size
    if file_size > UINT32_MAX + 8:
        raise ValueError(f"WAV is too large for a standard RIFF header: {path}")
    with path.open("r+b") as wav:
        header = wav.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            raise ValueError(f"Gnani output is not a standard RIFF/WAVE file: {path}")
        riff_size = int.from_bytes(header[4:8], "little")
        if riff_size == UINT32_MAX or riff_size != file_size - 8:
            wav.seek(4)
            wav.write((file_size - 8).to_bytes(4, "little"))

        offset = 12
        while offset + 8 <= file_size:
            wav.seek(offset)
            chunk_header = wav.read(8)
            chunk_id = chunk_header[:4]
            chunk_size = int.from_bytes(chunk_header[4:8], "little")
            if chunk_size == UINT32_MAX:
                if chunk_id != b"data":
                    raise ValueError(f"Unsupported oversized WAV chunk {chunk_id!r} in {path}")
                actual_size = file_size - offset - 8
                wav.seek(offset + 4)
                wav.write(actual_size.to_bytes(4, "little"))
                return
            offset += 8 + chunk_size + (chunk_size & 1)
            if chunk_id == b"data":
                return
        raise ValueError(f"WAV has no valid data chunk: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio_folder", type=Path, help="Folder containing customer audio files")
    parser.add_argument("--output", type=Path, default=Path("sample_outputs"), help="Output directory")
    parser.add_argument("--language", default="en-IN", help="Gnani STT language code such as en-IN or hi-IN")
    parser.add_argument("--reply-language", default="en-IN", help="Gnani TTS language code such as en-IN or hi-en")
    args = parser.parse_args()
    load_dotenv()
    if not os.getenv("GNANI_API_KEY"):
        raise SystemExit("Set GNANI_API_KEY in the environment before running voice batches.")
    files = sorted(p for p in args.audio_folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO)
    if not files:
        raise SystemExit(f"No supported audio files found in {args.audio_folder}")
    args.output.mkdir(parents=True, exist_ok=True)

    # The SDK API follows the capstone brief. No non-Gnani speech fallback is used.
    from gnani.stt import GnaniSTTClient
    from gnani.tts import GnaniTTSClient
    stt, tts = GnaniSTTClient(), GnaniTTSClient()
    results = []
    for audio_path in files:
        heard = stt.transcribe(str(audio_path), language_code=args.language)["transcript"]
        if not heard.strip():
            reply, sources = "Sorry, I didn't catch that. Could you say it again?", []
        else:
            result = answer(heard)
            reply, sources = result["answer"], result["evidence"]
        output_audio = args.output / f"{audio_path.stem}_reply.wav"
        tts.synthesize(reply, voice="Kaveri", model="timbre-v2.5",
                       language=args.reply_language, output_file=str(output_audio))
        normalize_wav_header(output_audio)
        item = {"input_audio": audio_path.name, "transcript": heard,
                "reply": reply, "sources": sources, "output_audio": output_audio.name}
        (args.output / f"{audio_path.stem}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(item)
        print(f"{audio_path.name}: {heard} -> {output_audio}")
    (args.output / "batch_manifest.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

