# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================

"""
Setup.py
"""

from setuptools import setup


setup(
    name='avalon',
    version='0.1.0',
    author='Hybrid Labs',
    author_email='hello@hy.bridlabs.com',
    packages=['avalon'],
    entry_points={'console_scripts': ['avalon = avalon.cli:main']},
    url='https://github.com/hybrid-labs/avalon',
    license='MIT',
    description='Avalon web framework',
    long_description=open('README').read(),
    install_requires=[
        'tornado >= 3.2.0',
        'sockjs-tornado >= 1.0.0',
        'bottle >= 0.12.0',
        'lxml >= 3.2.3',
        'motor >= 0.1.2'
    ],
)
