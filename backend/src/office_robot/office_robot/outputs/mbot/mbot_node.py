#!/usr/bin/env python3
"""
outputs/mbot/mbot_node.py — mBot command output.

Subscribes: /outputs/mbot/command  (String, JSON MbotCommandPayload)

Now:  prints the command to the terminal in cyan.
Next: when mBot is physically connected, set the 'serial_port' ROS param
      (e.g. '/dev/ttyUSB0') and the node will send the character over serial.

Command characters:
  F → FORWARD
  B → BACKWARD
  R → RIGHT
  L → LEFT
  S → STOP
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from office_robot.interfaces.schemas import MbotCommandPayload, load

LABELS = {'F': 'FORWARD', 'B': 'BACKWARD', 'R': 'RIGHT', 'L': 'LEFT', 'S': 'STOP'}

# ANSI cyan for mBot output so it's visually distinct from the green robot responses
CYAN = '\033[96m'
NC = '\033[0m'


class MbotNode(Node):
    def __init__(self):
        super().__init__('mbot_node')

        self.declare_parameter('serial_port', '')
        self._port = self.get_parameter('serial_port').get_parameter_value().string_value

        self._serial = None
        if self._port:
            self._open_serial()
        else:
            self.get_logger().info(
                'mBot node ready — terminal only (serial_port not set).'
            )

        self._sub = self.create_subscription(
            String, '/outputs/mbot/command', self._on_command, 10)

    def _open_serial(self):
        try:
            import serial
            self._serial = serial.Serial(self._port, baudrate=9600, timeout=1)
            self.get_logger().info(f'mBot node ready — serial: {self._port}')
        except Exception as exc:
            self.get_logger().error(
                f'Cannot open serial port {self._port}: {exc}. '
                f'Falling back to terminal only.'
            )
            self._serial = None

    def _on_command(self, msg: String):
        payload: MbotCommandPayload = load(msg.data)
        cmd = payload.get('command', '')
        source = payload.get('source_text', '')
        label = LABELS.get(cmd, '?')

        print(
            f'\n{CYAN}[mBot]{NC}  Sending: {cmd}  ({label})'
            f'  ←  "{source}"\n',
            flush=True,
        )

        if self._serial:
            try:
                self._serial.write(cmd.encode())
            except Exception as exc:
                self.get_logger().error(f'Serial write failed: {exc}')

    def destroy_node(self):
        if self._serial and self._serial.is_open:
            self._serial.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MbotNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
