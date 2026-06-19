from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'office_robot'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Shailesh',
    maintainer_email='shaileshrajendran@gmail.com',
    description='Office robot — layered voice pipeline',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # inputs/mic
            'mic_node         = office_robot.inputs.mic.mic_node:main',
            'asr_node         = office_robot.inputs.mic.asr_node:main',
            # brain
            'brain_node       = office_robot.brain.brain_node:main',
            # brain/classifiers
            'qa_node          = office_robot.brain.classifiers.qa.qa_node:main',
            'navigation_node  = office_robot.brain.classifiers.navigation.navigation_node:main',
            # outputs
            'tts_node         = office_robot.outputs.speaker.tts_node:main',
            'mbot_node        = office_robot.outputs.mbot.mbot_node:main',
        ],
    },
)
