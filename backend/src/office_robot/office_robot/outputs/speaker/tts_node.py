#!/usr/bin/env python3
"""
outputs/speaker/tts_node.py — human-voice TTS via Piper, espeak-ng fallback.

Subscribes: /outputs/speaker/text  (std_msgs/String, JSON SpeakerTextPayload)

Primary:  Piper TTS  — neural offline voice, sounds natural.
          Install:  run install_piper.sh from the repo root.
          Binary:   /usr/local/lib/piper/piper
          Voice:    /usr/local/share/piper-voices/en_US-lessac-medium.onnx

Fallback: espeak-ng — robotic but always available.

USB speaker: set 'alsa_device' param to 'hw:CARD=<name>,DEV=0' if the USB
             speaker is not the system default (find name with `aplay -l`).
"""

import os
import queue
import subprocess
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from office_robot.interfaces.schemas import SpeakerTextPayload, load

PIPER_BIN = '/usr/local/lib/piper/piper'
PIPER_VOICE_DEFAULT = '/usr/local/share/piper-voices/en_US-lessac-medium.onnx'
PIPER_RATE = '22050'  # en_US-lessac-medium outputs at 22050 Hz


class TTSNode(Node):
    def __init__(self):
        super().__init__('tts_node')

        self.declare_parameter('alsa_device', '')
        self.declare_parameter('piper_voice', PIPER_VOICE_DEFAULT)

        self._alsa = self.get_parameter('alsa_device').get_parameter_value().string_value
        self._voice = self.get_parameter('piper_voice').get_parameter_value().string_value

        self._use_piper = self._check_piper()

        self._q: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._speak_loop, daemon=True, name='tts').start()

        self._sub = self.create_subscription(
            String, '/outputs/speaker/text', self._on_text, 10)

        engine = 'Piper (neural)' if self._use_piper else 'espeak-ng (robotic fallback — run install_piper.sh)'
        self.get_logger().info(f'TTS node ready — {engine}')

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _check_piper(self) -> bool:
        missing = []
        if not os.path.exists(PIPER_BIN):
            missing.append(f'binary ({PIPER_BIN})')
        if not os.path.exists(self._voice):
            missing.append(f'voice model ({self._voice})')
        if missing:
            self.get_logger().warn(
                f'Piper not ready — missing: {", ".join(missing)}. '
                f'Run install_piper.sh to get the human voice. '
                f'Using espeak-ng for now.'
            )
            return False
        return True

    # ── Subscriber ─────────────────────────────────────────────────────────────

    def _on_text(self, msg: String):
        payload: SpeakerTextPayload = load(msg.data)
        text = payload.get('text', '').strip()
        if not text:
            return
        print(f'\n\033[92m[Robot]\033[0m {text}\n', flush=True)
        self._q.put(text)

    # ── Speak loop (serialises responses so they don't overlap) ────────────────

    def _speak_loop(self):
        while True:
            text = self._q.get()
            try:
                if self._use_piper:
                    self._speak_piper(text)
                else:
                    self._speak_espeak(text)
            except Exception as exc:
                self.get_logger().error(f'TTS error: {exc}')
            finally:
                self._q.task_done()

    # ── Piper ──────────────────────────────────────────────────────────────────

    def _speak_piper(self, text: str):
        # Piper reads from stdin, emits raw 16-bit mono PCM on stdout.
        # We pipe that straight to aplay.
        aplay_cmd = ['aplay', '-q', '-r', PIPER_RATE, '-f', 'S16_LE', '-c', '1']
        if self._alsa:
            aplay_cmd += ['-D', self._alsa]

        piper_proc = subprocess.Popen(
            [PIPER_BIN, '--model', self._voice, '--output-raw', '--quiet'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        aplay_proc = subprocess.Popen(
            aplay_cmd,
            stdin=piper_proc.stdout,
            stderr=subprocess.DEVNULL,
        )
        piper_proc.stdin.write(text.encode())
        piper_proc.stdin.close()
        piper_proc.wait()
        aplay_proc.wait()

    # ── espeak-ng fallback ────────────────────────────────────────────────────

    def _speak_espeak(self, text: str):
        cmd = ['espeak-ng', '-v', 'en-us', '-s', '145', text]
        if self._alsa:
            tts = subprocess.Popen(cmd + ['--stdout'], stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL)
            subprocess.run(['aplay', '-D', self._alsa], stdin=tts.stdout,
                           stderr=subprocess.DEVNULL)
            tts.wait()
        else:
            subprocess.run(cmd, timeout=60, stderr=subprocess.DEVNULL)


def main(args=None):
    rclpy.init(args=args)
    node = TTSNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
