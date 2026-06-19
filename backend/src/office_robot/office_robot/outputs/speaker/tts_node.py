#!/usr/bin/env python3
"""
outputs/speaker/tts_node.py — TTS output via espeak-ng + terminal print.

Subscribes: /outputs/speaker/text  (std_msgs/String, JSON SpeakerTextPayload)

Responses are queued so overlapping messages are spoken in order.
Terminal output is colour-coded green to distinguish from ROS2 logs.

USB speaker: espeak-ng uses the default ALSA output device.
  If your USB speaker is not the default, set the 'alsa_device' ROS param
  to the device string from `aplay -l`, e.g. "hw:CARD=Speaker,DEV=0".
"""

import queue
import subprocess
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from office_robot.interfaces.schemas import SpeakerTextPayload, load

TTS_VOICE = 'en-us'
TTS_SPEED = '145'    # words per minute (default 175)
TTS_PITCH = '50'     # 0–99


class TTSNode(Node):
    def __init__(self):
        super().__init__('tts_node')

        self.declare_parameter('alsa_device', '')
        self._alsa_device = (
            self.get_parameter('alsa_device').get_parameter_value().string_value
        )

        self._q: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._speak_loop, daemon=True, name='tts').start()

        self._sub = self.create_subscription(
            String, '/outputs/speaker/text', self._on_text, 10)

        self.get_logger().info('TTS node ready (espeak-ng).')

    def _on_text(self, msg: String):
        payload: SpeakerTextPayload = load(msg.data)
        text = payload.get('text', '').strip()
        if not text:
            return
        print(f'\n\033[92m[Robot]\033[0m {text}\n', flush=True)
        self._q.put(text)

    def _speak_loop(self):
        while True:
            text = self._q.get()
            self._speak(text)
            self._q.task_done()

    def _speak(self, text: str):
        cmd = ['espeak-ng', '-v', TTS_VOICE, '-s', TTS_SPEED, '-p', TTS_PITCH, text]

        if self._alsa_device:
            cmd += ['--stdout']
            try:
                tts_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
                subprocess.run(
                    ['aplay', '-D', self._alsa_device],
                    stdin=tts_proc.stdout,
                    timeout=60,
                    check=True,
                )
                tts_proc.wait()
            except Exception as exc:
                self.get_logger().error(f'TTS pipe error: {exc}')
        else:
            try:
                subprocess.run(cmd, check=True, timeout=60)
            except FileNotFoundError:
                self.get_logger().error('espeak-ng not found: sudo apt install espeak-ng')
            except subprocess.TimeoutExpired:
                self.get_logger().warn('TTS timed out.')
            except subprocess.CalledProcessError as exc:
                self.get_logger().error(f'espeak-ng error: {exc}')


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
