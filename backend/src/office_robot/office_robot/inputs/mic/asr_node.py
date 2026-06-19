#!/usr/bin/env python3
"""
inputs/mic/asr_node.py — speech-to-text via faster-whisper.

Subscribes: /inputs/mic/audio_segment  (std_msgs/UInt8MultiArray)
  — 16-bit PCM mono 16000 Hz, one complete utterance per message

Publishes:  /inputs/mic/transcript  (std_msgs/String)

CUDA note (JetPack 6.1 / aarch64):
  The PyPI ctranslate2 aarch64 wheel is CPU-only. This node detects this
  and falls back to CPU int8 automatically — still fast via ARM NEON SIMD.
  For GPU: compile ctranslate2 4.4.x from source (see install.sh).
"""

import numpy as np
from faster_whisper import WhisperModel

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, UInt8MultiArray

ASR_RATE = 16000
# base.en: ~150 MB, ~0.5–2 s on CPU int8 for typical utterances.
# Change to tiny.en for lower latency, small.en for higher accuracy.
MODEL_SIZE = 'base.en'


class ASRNode(Node):
    def __init__(self):
        super().__init__('asr_node')
        self._model = self._load_model()
        self._pub = self.create_publisher(String, '/inputs/mic/transcript', 10)
        self._sub = self.create_subscription(
            UInt8MultiArray, '/inputs/mic/audio_segment', self._on_audio, 10)

    def _load_model(self) -> WhisperModel:
        for device, ctype in [('cuda', 'float16'), ('cpu', 'int8')]:
            try:
                self.get_logger().info(f'Loading Whisper "{MODEL_SIZE}" on {device} ({ctype}) …')
                model = WhisperModel(MODEL_SIZE, device=device, compute_type=ctype)
                self.get_logger().info(f'Whisper ready on {device}.')
                return model
            except Exception as exc:
                self.get_logger().warn(f'{device} unavailable: {exc}')
        raise RuntimeError('Could not load Whisper on CUDA or CPU.')

    def _on_audio(self, msg: UInt8MultiArray):
        audio_f32 = (
            np.frombuffer(bytes(msg.data), dtype=np.int16)
            .astype(np.float32) / 32768.0
        )
        segments, _ = self._model.transcribe(
            audio_f32,
            language='en',
            beam_size=1,
            best_of=1,
            vad_filter=True,
            vad_parameters={'min_silence_duration_ms': 200},
        )
        transcript = ' '.join(seg.text for seg in segments).strip()
        if transcript:
            self.get_logger().info(f'[transcript] {transcript}')
            self._pub.publish(String(data=transcript))


def main(args=None):
    rclpy.init(args=args)
    node = ASRNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
