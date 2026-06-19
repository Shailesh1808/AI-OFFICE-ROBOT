from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([

        # ── inputs/mic ─────────────────────────────────────────────────────────
        Node(
            package='office_robot',
            executable='mic_node',
            name='mic_node',
            output='screen',
            parameters=[{
                # Substring matched against PyAudio device name (case-insensitive).
                # Robot (Jetson + XVF3800): keep as 'xvf'
                # Laptop / WSL2:           change to '' to use the system default mic,
                #                          or set to a substring from find_audio_device.py
                'device_name_hint': 'xvf',
            }],
        ),
        Node(
            package='office_robot',
            executable='asr_node',
            name='asr_node',
            output='screen',
        ),

        # ── brain ──────────────────────────────────────────────────────────────
        Node(
            package='office_robot',
            executable='brain_node',
            name='brain_node',
            output='screen',
        ),

        # ── brain/classifiers ─────────────────────────────────────────────────
        Node(
            package='office_robot',
            executable='qa_node',
            name='qa_node',
            output='screen',
        ),

        # ── outputs ────────────────────────────────────────────────────────────
        Node(
            package='office_robot',
            executable='tts_node',
            name='tts_node',
            output='screen',
            parameters=[{
                # Leave empty to use the system default ALSA output device.
                # If the USB speaker is not the default:
                #   run `aplay -l` on the Jetson to find the card name, then set e.g.:
                #   'alsa_device': 'hw:CARD=Speaker,DEV=0'
                'alsa_device': '',
            }],
        ),

    ])
