from __future__ import annotations

import math
import wave
from collections.abc import Iterator
from pathlib import Path

from subtitles.audio.base import AudioCapturer
from subtitles.audio.models import (
    AudioCaptureConfig,
    AudioChunk,
    AudioCaptureDevice,
    AudioCaptureError,
    AudioCaptureResult,
)


class PyAudioWasapiLoopbackCapturer(AudioCapturer):
    def _load_pyaudio(self):
        try:
            import pyaudiowpatch as pyaudio
        except ImportError as exc:
            raise AudioCaptureError(
                "Missing dependency: PyAudioWPatch. Install dependencies with:\n"
                "pip install -r requirements.txt"
            ) from exc

        return pyaudio

    def _build_device(self, raw_device: dict, default_index: int | None) -> AudioCaptureDevice:
        return AudioCaptureDevice(
            index=int(raw_device["index"]),
            name=str(raw_device["name"]),
            max_input_channels=int(raw_device.get("maxInputChannels", 0)),
            default_sample_rate=int(float(raw_device.get("defaultSampleRate", 48000))),
            is_default=int(raw_device["index"]) == default_index,
            is_loopback=True,
        )

    def list_devices(self) -> list[AudioCaptureDevice]:
        pyaudio = self._load_pyaudio()

        with pyaudio.PyAudio() as audio:
            default_loopback = audio.get_default_wasapi_loopback()
            default_index = None if default_loopback is None else default_loopback["index"]
            devices = [
                self._build_device(device, default_index)
                for device in audio.get_loopback_device_info_generator()
            ]

        if not devices:
            raise AudioCaptureError(
                "No WASAPI loopback devices were found. "
                "Make sure Windows has an active playback device."
            )

        return devices

    def resolve_device(self, device_name: str | None = None) -> AudioCaptureDevice:
        devices = self.list_devices()
        if not device_name:
            for device in devices:
                if device.is_default:
                    return device
            return devices[0]

        lowered = device_name.casefold()
        for device in devices:
            if device.name.casefold() == lowered:
                return device

        for device in devices:
            if lowered in device.name.casefold():
                return device

        available = ", ".join(device.name for device in devices)
        raise AudioCaptureError(
            f"Loopback device not found: {device_name}\nAvailable devices: {available}"
        )

    def _validate_common_config(
        self,
        device: AudioCaptureDevice,
        config: AudioCaptureConfig,
    ) -> None:
        if config.sample_rate <= 0:
            raise AudioCaptureError("--sample-rate must be greater than 0.")
        if config.channels <= 0:
            raise AudioCaptureError("--channels must be greater than 0.")
        if config.frames_per_buffer <= 0:
            raise AudioCaptureError("--frames-per-buffer must be greater than 0.")
        if config.channels > device.max_input_channels:
            raise AudioCaptureError(
                f"Requested {config.channels} channel(s), but device "
                f"'{device.name}' supports at most {device.max_input_channels}."
            )

    def _validate_capture_to_file_config(
        self,
        device: AudioCaptureDevice,
        config: AudioCaptureConfig,
    ) -> None:
        self._validate_common_config(device, config)
        if config.seconds <= 0:
            raise AudioCaptureError("--seconds must be greater than 0.")

    def _write_wave_file(
        self,
        output_path: Path,
        frame_bytes: bytes,
        channels: int,
        sample_rate: int,
        sample_width: int,
    ) -> None:
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(frame_bytes)

    def _open_input_stream(
        self,
        audio,
        pyaudio,
        device: AudioCaptureDevice,
        config: AudioCaptureConfig,
    ):
        return audio.open(
            format=pyaudio.paInt16,
            channels=config.channels,
            rate=config.sample_rate,
            frames_per_buffer=config.frames_per_buffer,
            input=True,
            input_device_index=device.index,
        )

    def iter_chunks(self, config: AudioCaptureConfig) -> Iterator[AudioChunk]:
        pyaudio = self._load_pyaudio()
        device = self.resolve_device(config.device_name)
        self._validate_common_config(device, config)

        with pyaudio.PyAudio() as audio:
            sample_width = audio.get_sample_size(pyaudio.paInt16)
            with self._open_input_stream(audio, pyaudio, device, config) as stream:
                current_time = 0.0
                while True:
                    data = stream.read(
                        config.frames_per_buffer,
                        exception_on_overflow=False,
                    )
                    frames = len(data) // (config.channels * sample_width)
                    duration = frames / config.sample_rate
                    yield AudioChunk(
                        data=data,
                        sample_rate=config.sample_rate,
                        channels=config.channels,
                        sample_width=sample_width,
                        frames=frames,
                        start_time=current_time,
                        end_time=current_time + duration,
                        device=device,
                    )
                    current_time += duration

    def capture_to_file(
        self,
        output_path: Path,
        config: AudioCaptureConfig,
    ) -> AudioCaptureResult:
        pyaudio = self._load_pyaudio()
        device = self.resolve_device(config.device_name)
        self._validate_capture_to_file_config(device, config)

        chunk_count = max(
            1,
            math.ceil(config.seconds * config.sample_rate / config.frames_per_buffer),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with pyaudio.PyAudio() as audio:
            sample_width = audio.get_sample_size(pyaudio.paInt16)
            with self._open_input_stream(audio, pyaudio, device, config) as stream:
                chunks: list[bytes] = []
                for _ in range(chunk_count):
                    chunks.append(
                        stream.read(
                            config.frames_per_buffer,
                            exception_on_overflow=False,
                        )
                    )

        self._write_wave_file(
            output_path=output_path,
            frame_bytes=b"".join(chunks),
            channels=config.channels,
            sample_rate=config.sample_rate,
            sample_width=sample_width,
        )

        return AudioCaptureResult(
            output_path=output_path,
            device=device,
            seconds=config.seconds,
            sample_rate=config.sample_rate,
            channels=config.channels,
            frames_per_buffer=config.frames_per_buffer,
        )
