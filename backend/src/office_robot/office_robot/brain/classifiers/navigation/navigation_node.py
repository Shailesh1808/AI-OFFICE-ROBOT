#!/usr/bin/env python3
"""
brain/classifiers/navigation/navigation_node.py — voice → mBot command mapper.

Subscribes:
  /brain/navigation  (String, JSON BrainNavigationPayload)
  /brain/stop        (String, JSON BrainStopPayload)  — stop is a movement command

Publishes:
  /outputs/mbot/command  (String, JSON MbotCommandPayload)

Command mapping:
  forward / ahead / go      → F
  backward / back / reverse → B
  right / turn right        → R
  left  / turn left         → L
  stop  / halt / freeze     → S
"""

import re

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from office_robot.interfaces.schemas import (
    BrainNavigationPayload,
    BrainStopPayload,
    MbotCommandPayload,
    dump,
    load,
)

# Ordered — first match wins
COMMAND_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\b(forward|ahead|straight)\b'), 'F'),
    (re.compile(r'\b(backward|back|reverse|behind)\b'), 'B'),
    (re.compile(r'\b(right)\b'), 'R'),
    (re.compile(r'\b(left)\b'), 'L'),
    (re.compile(r'\b(stop|halt|freeze|pause)\b'), 'S'),
]

LABELS = {'F': 'FORWARD', 'B': 'BACKWARD', 'R': 'RIGHT', 'L': 'LEFT', 'S': 'STOP'}


def classify(text: str) -> str | None:
    lower = text.lower()
    for pattern, cmd in COMMAND_MAP:
        if pattern.search(lower):
            return cmd
    return None


class NavigationNode(Node):
    def __init__(self):
        super().__init__('navigation_node')

        self._sub_nav = self.create_subscription(
            String, '/brain/navigation', self._on_navigation, 10)
        self._sub_stop = self.create_subscription(
            String, '/brain/stop', self._on_stop, 10)
        self._pub = self.create_publisher(String, '/outputs/mbot/command', 10)

        self.get_logger().info('Navigation node ready.')

    def _on_navigation(self, msg: String):
        payload: BrainNavigationPayload = load(msg.data)
        text = payload.get('text', '')
        cmd = classify(text)
        if cmd:
            self._publish(cmd, text)
        else:
            self.get_logger().warn(f'No command mapped from: {text!r}')

    def _on_stop(self, msg: String):
        self._publish('S', 'stop')

    def _publish(self, cmd: str, source_text: str):
        self.get_logger().info(f'Mapped {source_text!r} → {cmd} ({LABELS[cmd]})')
        out: MbotCommandPayload = {
            'command': cmd,
            'source_text': source_text,
            'source': 'navigation',
        }
        self._pub.publish(String(data=dump(out)))


def main(args=None):
    rclpy.init(args=args)
    node = NavigationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
