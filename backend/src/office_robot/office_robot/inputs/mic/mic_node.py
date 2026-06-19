#!/usr/bin/env python3
"""
inputs/mic/mic_node.py — microphone capture + VAD.

Works with:
  - XMOS XVF3800 (4-mic array, robot hardware)
  - Any standard USB microphone or laptop mic

Uses arecord (ALSA plughw) for capture — bypasses PyAudio entirely, which
avoids channel-count validation failures and Python 3.10 C-API issues.
Rate conversion and channel downmix are handled by the ALSA plug layer.

Publishes: /inputs/mic/audio_segment  (std_msgs/UInt8MultiArray)
  — 16-bit PCM, mono, 16000 Hz, little-endian; one complete utterance per msg
"""

import collections
import re
import subprocess
import threading
import time

import numpy as np
import webrtcvad

import rclpy
from rclpy.node import Node
from std_msgs.msg import UInt8MultiArray

# ── Audio constants ────────────────────────────────────────────────────────────
ASR_RATE = 16000
SAMPLE_WIDTH = 2           # 16-bit PCM

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

        self._pre_buf: collections.deque[bytes] = collections.deque(maxlen=PRE_SPEECH_FRAMES)
        self._speech_frames: list[bytes] = []
        self._is_speaking = False
        self._voiced_count = 0
        self._silence_count = 0

        alsa_dev = self._find_alsa_device(hint)
        self._proc, self._capture_channels = self._open_capture(hint, alsa_dev)

        threading.Thread(target=self._capture_loop, daemon=True, name='mic_capture').start()

        self.get_logger().info(
            f'Mic node running — {alsa_dev} @ {ASR_RATE} Hz, {self._capture_channels}ch→mono'
        )

    # ── Device detection ───────────────────────────────────────────────────────

    def _find_alsa_device(self, hint: str) -> str:
        """Return plughw device string for the first input card matching hint."""
        try:
            result = subprocess.run(
                ['arecord', '-l'], capture_output=True, text=True, timeout=5)
            lines = result.stdout.splitlines()
        except Exception:
            lines = []

        aliases = [a for a in (hint, 'respeaker', 'xmos', 'xvf', 'vocal') if a]

        self.get_logger().info('Available ALSA capture devices:')
        first_card = first_dev = None

        for line in lines:
            if not line.startswith('card '):
                continue
            self.get_logger().info(f'  {line}')
            m = re.match(r'card (\d+): \S+ \[([^\]]+)\], device (\d+):', line)
            if not m:
                continue
            card_num, card_name, dev_num = m.group(1), m.group(2), m.group(3)

            for alias in aliases:
                if alias.lower() in card_name.lower():
                    dev_str = f'plughw:{card_num},{dev_num}'
                    self.get_logger().info(
                        f'Selected {dev_str!r} via "{alias}" ({card_name})')
                    return dev_str

            if first_card is None:
                first_card, first_dev = card_num, dev_num

        if first_card is not None:
            dev_str = f'plughw:{first_card},{first_dev}'
            self.get_logger().warn(
                f'No XVF3800 found — using first capture device: {dev_str}')
            return dev_str

        self.get_logger().warn('No capture devices found — using plughw:0,0')
        return 'plughw:0,0'

    def _find_pulse_source(self, hint: str) -> str:
        """Return the PulseAudio source name matching hint, or empty string."""
        try:
            r = subprocess.run(
                ['pactl', 'list', 'short', 'sources'],
                capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                parts = line.split('\t')
                if len(parts) < 2:
                    continue
                name = parts[1]
                for alias in (hint, 'xvf', 'respeaker', 'xmos', 'vocal', 'array'):
                    if alias and alias.lower() in name.lower():
                        return name
        except Exception:
            pass
        return ''

    def _open_capture(self, hint: str, alsa_dev: str) -> tuple:
        """Try parecord (PulseAudio) first, then arecord with direct ALSA."""
        # 1. PulseAudio — preferred; PulseAudio owns hw devices on desktop Linux
        pulse_src = self._find_pulse_source(hint)
        if pulse_src:
            cmd = ['parecord', '-d', pulse_src,
                   f'--rate={ASR_RATE}', '--format=s16le', '--channels=1', '--raw']
            self.get_logger().info(f'Trying PulseAudio: {" ".join(cmd)}')
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(0.4)
            if proc.poll() is None:
                self.get_logger().info(f'Opened via PulseAudio source: {pulse_src}')
                return proc, 1
            err = proc.stderr.read().decode(errors='replace').strip()
            self.get_logger().warn(f'parecord failed: {err}')

        # 2. Direct ALSA — works when PulseAudio is not running
        for channels in (2, 1, 4):
            cmd = ['arecord', '-D', alsa_dev, '-f', 'S16_LE',
                   '-r', str(ASR_RATE), '-c', str(channels), '-t', 'raw']
            self.get_logger().info(f'Trying ALSA: {" ".join(cmd)}')
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(0.4)
            if proc.poll() is None:
                self.get_logger().info(f'Opened via ALSA with {channels} channel(s)')
                return proc, channels
            err = proc.stderr.read().decode(errors='replace').strip()
            self.get_logger().warn(f'arecord {channels}ch failed: {err}')

        raise RuntimeError(f'Cannot open capture for {alsa_dev}')

    # ── Capture loop ───────────────────────────────────────────────────────────

    def _capture_loop(self):
        ch = self._capture_channels
        read_bytes = VAD_FRAME_BYTES * ch * 4  # read in larger chunks for efficiency
        buf = b''
        while rclpy.ok():
            chunk = self._proc.stdout.read(read_bytes)
            if not chunk:
                self.get_logger().error('arecord process ended unexpectedly')
                break
            buf += chunk
            frame_bytes_ch = VAD_FRAME_BYTES * ch
            while len(buf) >= frame_bytes_ch:
                raw = buf[:frame_bytes_ch]
                buf = buf[frame_bytes_ch:]
                # Downmix to mono by taking channel 0 (every ch-th sample)
                if ch > 1:
                    samples = np.frombuffer(raw, dtype=np.int16)
                    raw = samples[::ch].copy().tobytes()
                try:
                    self._vad_step(raw)
                except Exception as exc:
                    self.get_logger().error(f'VAD error: {exc}')

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
            self._proc.terminate()
            self._proc.wait(timeout=2)
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
