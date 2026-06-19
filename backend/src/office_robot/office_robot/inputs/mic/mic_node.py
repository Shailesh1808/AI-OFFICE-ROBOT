#!/usr/bin/env python3
"""
inputs/mic/mic_node.py — microphone capture + VAD.

Works with:
  - XMOS XVF3800 (4-mic array, 2-ch USB, robot hardware)
  - Any standard laptop/desktop microphone (1 or 2 ch, WSL2 / native Linux)

Channel count and sample rate are auto-detected from the device.

Publishes: /inputs/mic/audio_segment  (std_msgs/UInt8MultiArray)
  — 16-bit PCM, mono, 16000 Hz, little-endian; one complete utterance per msg
"""

import audioop
import collections
import queue
import threading

import numpy as np
import pyaudio
import webrtcvad

import rclpy
from rclpy.node import Node
from std_msgs.msg import UInt8MultiArray

# ── Audio constants ────────────────────────────────────────────────────────────
ASR_RATE = 16000
SAMPLE_WIDTH = 2           # 16-bit PCM
# CAPTURE_CHANNELS is auto-detected per device (see _open_stream)

VAD_FRAME_MS = 20          # webrtcvad supports 10 / 20 / 30 ms
VAD_FRAME_BYTES = int(ASR_RATE * VAD_FRAME_MS / 1000) * SAMPLE_WIDTH  # 640 bytes

# ── VAD tuning ─────────────────────────────────────────────────────────────────
VAD_MODE = 2               # 0–3; higher = more aggressive silence filtering
PRE_SPEECH_FRAMES = 10     # lookahead frames kept before onset  (200 ms)
SPEECH_ONSET_FRAMES = 5    # voiced frames needed to trigger onset (100 ms)
SILENCE_END_FRAMES = 30    # silent frames to close an utterance  (600 ms)
MAX_UTTERANCE_FRAMES = 1500  # hard cap: 30 s


class MicNode(Node):
    def __init__(self):
        super().__init__('mic_node')

        self.declare_parameter('device_name_hint', 'xvf')
        hint = self.get_parameter('device_name_hint').get_parameter_value().string_value

        self._pub = self.create_publisher(
            UInt8MultiArray, '/inputs/mic/audio_segment', 10)
        self._vad = webrtcvad.Vad(VAD_MODE)
        self._pa = pyaudio.PyAudio()

        self._device_idx = self._find_device(hint)
        self._stream, self._capture_rate, self._capture_channels = self._open_stream(self._device_idx)

        self._raw_q: queue.Queue[bytes] = queue.Queue(maxsize=300)
        self._ratecv_state = None
        self._vad_buf = b''

        self._pre_buf: collections.deque[bytes] = collections.deque(maxlen=PRE_SPEECH_FRAMES)
        self._speech_frames: list[bytes] = []
        self._is_speaking = False
        self._voiced_count = 0
        self._silence_count = 0

        threading.Thread(target=self._process_loop, daemon=True, name='mic_proc').start()

        self._stream.start_stream()
        name = self._pa.get_device_info_by_index(self._device_idx)['name']
        self.get_logger().info(
            f'Mic node running — [{self._device_idx}] {name!r} '
            f'@ {self._capture_rate} Hz, {self._capture_channels}ch'
        )

    # ── Device detection ───────────────────────────────────────────────────────

    def _find_device(self, hint: str) -> int:
        count = self._pa.get_device_count()
        self.get_logger().info('Available audio input devices:')
        first_input = None

        for i in range(count):
            info = self._pa.get_device_info_by_index(i)
            if info['maxInputChannels'] < 1:
                continue
            name = info['name']
            self.get_logger().info(f'  [{i}] {name}  ({int(info["defaultSampleRate"])} Hz, {int(info["maxInputChannels"])}ch)')
            if first_input is None:
                first_input = i
            # Match XVF3800 aliases first; hint='xvf' won't match a laptop mic
            # so we fall through to the default device naturally
            for alias in (hint, 'respeaker', 'xmos', 'xvf', 'vocal'):
                if alias.lower() in name.lower():
                    self.get_logger().info(f'Selected [{i}] via "{alias}"')
                    return i

        # Fall back to system default input (laptop mic on WSL2 / desktop)
        try:
            default_idx = self._pa.get_default_input_device_info()['index']
            self.get_logger().info(
                f'No XVF3800 found — using default input device [{default_idx}]. '
                f'Override with ROS param device_name_hint if needed.'
            )
            return default_idx
        except OSError:
            pass

        idx = first_input if first_input is not None else 0
        self.get_logger().warn(f'Using first available input device [{idx}].')
        return idx

    def _open_stream(self, device_idx: int):
        """Try common rates and channel counts; auto-detect what the device supports."""
        info = self._pa.get_device_info_by_index(device_idx)
        max_ch = int(info['maxInputChannels'])
        # Prefer stereo for XVF3800; fall back to mono for laptop mics
        channel_options = [2, 1] if max_ch >= 2 else [1]

        for rate in (16000, 48000):
            for channels in channel_options:
                chunk = int(rate * VAD_FRAME_MS / 1000)
                try:
                    stream = self._pa.open(
                        format=pyaudio.paInt16,
                        channels=channels,
                        rate=rate,
                        input=True,
                        input_device_index=device_idx,
                        frames_per_buffer=chunk,
                        stream_callback=self._audio_cb,
                    )
                    self.get_logger().info(
                        f'Audio stream opened: {rate} Hz, {channels}ch'
                    )
                    return stream, rate, channels
                except OSError:
                    continue

        raise RuntimeError(
            f'Cannot open device [{device_idx}] at any supported rate/channel combo. '
            f'Run find_audio_device.py to inspect the device.'
        )

    # ── PyAudio callback ───────────────────────────────────────────────────────

    def _audio_cb(self, in_data, frame_count, time_info, status):
        try:
            self._raw_q.put_nowait(in_data)
        except queue.Full:
            pass
        return (None, pyaudio.paContinue)

    # ── Processing thread ──────────────────────────────────────────────────────

    def _process_loop(self):
        while rclpy.ok():
            try:
                raw = self._raw_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._process_chunk(raw)
            except Exception as exc:
                self.get_logger().error(f'Process error: {exc}')

    def _process_chunk(self, raw_bytes: bytes):
        samples = np.frombuffer(raw_bytes, dtype=np.int16)
        # Stereo → mono: take channel 0 (every other sample).
        # Mono: use as-is.
        mono = samples[::self._capture_channels].copy()

        if self._capture_rate != ASR_RATE:
            mono_bytes, self._ratecv_state = audioop.ratecv(
                mono.tobytes(), SAMPLE_WIDTH, 1,
                self._capture_rate, ASR_RATE, self._ratecv_state,
            )
        else:
            mono_bytes = mono.tobytes()

        self._vad_buf += mono_bytes
        while len(self._vad_buf) >= VAD_FRAME_BYTES:
            frame = self._vad_buf[:VAD_FRAME_BYTES]
            self._vad_buf = self._vad_buf[VAD_FRAME_BYTES:]
            self._vad_step(frame)

    # ── VAD state machine ──────────────────────────────────────────────────────

    def _vad_step(self, frame: bytes):
        try:
            voiced = self._vad.is_speech(frame, ASR_RATE)
        except Exception:
            voiced = False

        if not self._is_speaking:
            self._pre_buf.append(frame)
            self._voiced_count = (self._voiced_count + 1) if voiced else max(0, self._voiced_count - 1)
            if self._voiced_count >= SPEECH_ONSET_FRAMES:
                self._is_speaking = True
                self._voiced_count = 0
                self._silence_count = 0
                self._speech_frames = list(self._pre_buf)
        else:
            self._speech_frames.append(frame)
            self._silence_count = (self._silence_count + 1) if not voiced else 0
            if (self._silence_count >= SILENCE_END_FRAMES
                    or len(self._speech_frames) >= MAX_UTTERANCE_FRAMES):
                self._publish_segment()

    def _publish_segment(self):
        if len(self._speech_frames) < 5:
            self._reset_vad()
            return
        audio_bytes = b''.join(self._speech_frames)
        duration = len(audio_bytes) / (ASR_RATE * SAMPLE_WIDTH)
        msg = UInt8MultiArray()
        msg.data = list(audio_bytes)
        self._pub.publish(msg)
        self.get_logger().info(f'Segment published: {duration:.2f}s')
        self._reset_vad()

    def _reset_vad(self):
        self._speech_frames = []
        self._is_speaking = False
        self._silence_count = 0
        self._voiced_count = 0

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def destroy_node(self):
        try:
            self._stream.stop_stream()
            self._stream.close()
        except Exception:
            pass
        try:
            self._pa.terminate()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MicNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
