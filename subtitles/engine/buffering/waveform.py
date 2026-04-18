from __future__ import annotations

from subtitles.audio import AudioChunk


def chunks_to_waveform(chunks: list[AudioChunk], target_sample_rate: int = 16000):
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: numpy. Install dependencies with:\n"
            "pip install numpy"
        ) from exc

    if not chunks:
        return np.empty(0, dtype=np.float32)

    first_chunk = chunks[0]
    if first_chunk.sample_width != 2:
        raise ValueError("Only 16-bit PCM audio chunks are currently supported.")
    if target_sample_rate <= 0:
        raise ValueError("target_sample_rate must be greater than 0.")

    pcm = np.frombuffer(b"".join(chunk.data for chunk in chunks), dtype=np.int16)
    channels = first_chunk.channels
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1)

    waveform = pcm.astype(np.float32) / 32768.0
    source_sample_rate = first_chunk.sample_rate

    if source_sample_rate == target_sample_rate:
        return waveform

    if waveform.size == 0:
        return waveform

    source_positions = np.arange(waveform.shape[0], dtype=np.float32)
    target_length = max(
        1,
        int(round(waveform.shape[0] * target_sample_rate / source_sample_rate)),
    )
    target_positions = np.linspace(
        0,
        waveform.shape[0] - 1,
        num=target_length,
        dtype=np.float32,
    )
    resampled = np.interp(target_positions, source_positions, waveform)
    return resampled.astype(np.float32)


def chunk_to_waveform(chunk: AudioChunk, target_sample_rate: int = 16000):
    return chunks_to_waveform([chunk], target_sample_rate=target_sample_rate)
