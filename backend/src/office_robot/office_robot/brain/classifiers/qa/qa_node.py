#!/usr/bin/env python3
"""
brain/classifiers/qa/qa_node.py — Q&A classifier using LLaMA 3.2 via ollama.

Subscribes: /brain/qa            (std_msgs/String, JSON BrainQAPayload)
Publishes:  /outputs/speaker/text (std_msgs/String, JSON SpeakerTextPayload)
"""

import threading

import requests

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from office_robot.interfaces.schemas import (
    BrainQAPayload,
    SpeakerTextPayload,
    dump,
    load,
)

OLLAMA_BASE = 'http://localhost:11434'
MODEL = 'llama3.2:3b'
REQUEST_TIMEOUT = 60

SYSTEM_PROMPT = (
    'You are a concise, helpful office robot assistant. '
    'Respond in 1–3 short sentences suitable for being read aloud. '
    'Be direct. No bullet points, no markdown, no lists.'
)


class QANode(Node):
    def __init__(self):
        super().__init__('qa_node')

        self._pub = self.create_publisher(String, '/outputs/speaker/text', 10)
        self._sub = self.create_subscription(
            String, '/brain/qa', self._on_question, 10)

        self._verify_ollama()
        self.get_logger().info(f'QA node ready — {MODEL}')

    def _verify_ollama(self):
        try:
            r = requests.get(f'{OLLAMA_BASE}/api/tags', timeout=5)
            r.raise_for_status()
            names = [m['name'] for m in r.json().get('models', [])]
            if any(MODEL.split(':')[0] in n for n in names):
                self.get_logger().info(f'"{MODEL}" found in ollama.')
            else:
                self.get_logger().warn(f'"{MODEL}" not found. Run: ollama pull {MODEL}')
        except requests.ConnectionError:
            self.get_logger().error('ollama unreachable. Run: ollama serve')

    def _on_question(self, msg: String):
        payload: BrainQAPayload = load(msg.data)
        question = payload.get('text', '').strip()
        if question:
            threading.Thread(
                target=self._query, args=(question,), daemon=True
            ).start()

    def _query(self, question: str):
        self.get_logger().info(f'Querying LLM: {question!r}')
        try:
            resp = requests.post(
                f'{OLLAMA_BASE}/api/generate',
                json={
                    'model': MODEL,
                    'prompt': question,
                    'system': SYSTEM_PROMPT,
                    'stream': False,
                    'options': {'temperature': 0.7, 'num_predict': 150},
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            answer = resp.json()['response'].strip()
        except requests.Timeout:
            answer = 'Sorry, the model took too long to respond.'
        except requests.ConnectionError:
            answer = 'I cannot reach the language model right now.'
        except Exception as exc:
            self.get_logger().error(f'LLM error: {exc}')
            answer = 'Sorry, I ran into an error.'

        self.get_logger().info(f'[answer] {answer}')
        out: SpeakerTextPayload = {'text': answer, 'source': 'qa'}
        self._pub.publish(String(data=dump(out)))


def main(args=None):
    rclpy.init(args=args)
    node = QANode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
