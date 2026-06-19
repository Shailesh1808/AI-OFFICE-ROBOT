#!/usr/bin/env python3
"""
brain/brain_node.py — wake word detection + intent routing.

Subscribes: /inputs/mic/transcript  (std_msgs/String)

Routes to (one topic per intent — new classifiers subscribe to their own topic):
  /brain/qa           (String, JSON BrainQAPayload)
  /brain/navigation   (String, JSON BrainNavigationPayload)  — future
  /brain/stop         (String, JSON BrainStopPayload)        — future

Wake word: "robot" (case-insensitive, can appear anywhere in the utterance).
"""

import re

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from office_robot.interfaces.schemas import (
    BrainQAPayload,
    BrainNavigationPayload,
    BrainStopPayload,
    dump,
)

WAKE_WORD = 'robot'
SOURCE = 'voice'

# Intent detection — first match wins; keep question last as catch-all.
INTENT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\b(stop|halt|freeze|pause|cancel)\b'),                         'stop'),
    (re.compile(r'\b(move|go|come|drive|navigate|forward|backward|turn|left|right|rotate)\b'), 'navigation'),
    (re.compile(r'\b(what|where|when|who|why|how|tell|explain|describe|is|are|can|will|should|does|do)\b'), 'question'),
]


def detect_intent(text: str) -> str:
    lower = text.lower()
    for pattern, label in INTENT_PATTERNS:
        if pattern.search(lower):
            return label
    return 'question'


class BrainNode(Node):
    def __init__(self):
        super().__init__('brain_node')

        self._sub = self.create_subscription(
            String, '/inputs/mic/transcript', self._on_transcript, 10)

        # One publisher per intent — classifiers subscribe to their own topic
        self._pub_qa = self.create_publisher(String, '/brain/qa', 10)
        self._pub_nav = self.create_publisher(String, '/brain/navigation', 10)
        self._pub_stop = self.create_publisher(String, '/brain/stop', 10)

        self.get_logger().info(f'Brain node ready — wake word: "{WAKE_WORD}"')

    def _on_transcript(self, msg: String):
        text = msg.data.strip()
        lower = text.lower()

        match = re.search(rf'\b{re.escape(WAKE_WORD)}\b', lower)
        if not match:
            return

        command = text[match.end():].strip(' ,.')
        if not command:
            self.get_logger().info('Wake word heard but no command followed.')
            return

        intent = detect_intent(command)
        self.get_logger().info(f'[{intent}] {command}')
        self._route(intent, command)

    def _route(self, intent: str, command: str):
        if intent == 'question':
            payload: BrainQAPayload = {'text': command, 'source': SOURCE}
            self._pub_qa.publish(String(data=dump(payload)))

        elif intent == 'navigation':
            payload: BrainNavigationPayload = {'text': command, 'source': SOURCE}
            self._pub_nav.publish(String(data=dump(payload)))

        elif intent == 'stop':
            payload: BrainStopPayload = {'source': SOURCE}
            self._pub_stop.publish(String(data=dump(payload)))


def main(args=None):
    rclpy.init(args=args)
    node = BrainNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
