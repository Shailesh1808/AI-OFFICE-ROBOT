#!/usr/bin/env python3
"""
find_audio_device.py — lists all audio devices seen by PyAudio.
Run this on the Jetson to find your XVF3800 device index and name.

Usage:
    python3 find_audio_device.py
"""

import pyaudio


def main():
    pa = pyaudio.PyAudio()
    count = pa.get_device_count()
    print(f'\nFound {count} audio device(s) total.\n')
    print(f'{"Idx":<5} {"In":<4} {"Out":<4} {"Rate":<8} Name')
    print('─' * 65)

    for i in range(count):
        info = pa.get_device_info_by_index(i)
        ch_in = int(info['maxInputChannels'])
        ch_out = int(info['maxOutputChannels'])
        rate = int(info['defaultSampleRate'])
        name = info['name']

        hints = []
        if 'xvf' in name.lower() or 'xmos' in name.lower():
            hints.append('← XVF3800 MIC')
        if 'respeaker' in name.lower():
            hints.append('← ReSpeaker MIC')
        if ch_in == 0 and ch_out > 0 and ('usb' in name.lower() or 'speaker' in name.lower()):
            hints.append('← possible USB SPEAKER')

        suffix = '  ' + ' / '.join(hints) if hints else ''
        print(f'{i:<5} {ch_in:<4} {ch_out:<4} {rate:<8} {name}{suffix}')

    pa.terminate()

    print()
    print('For the mic_node, set device_name_hint to a substring of the XVF3800 name.')
    print('For the tts_node, run  aplay -l  to list ALSA playback devices by card name.')
    print()


if __name__ == '__main__':
    main()
