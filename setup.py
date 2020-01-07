from setuptools import setup

import sys
import platform

with open("README.md", "r") as fh:
    long_description = fh.read()


setup(
    name="jarvis-sdk",
    version="0.0.16",
    packages=['jarvis_sdk'],
    description='JARVIS SDK Python Package',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://www.fashiondata.io/",
    author="Fashiondata Team",
    author_email="contact@fashiondata.io",
    license="GPLv3",
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3"
    ],
    install_requires=[
        'requests>=2.22.0',
        'firebase>=3.0.1',
        'pycryptodome>=1.6.0',
        'python_jwt',
        'gcloud',
        'sseclient',
        'requests-toolbelt',
        'google.auth'
    ],
    keywords=['pip', 'fashiondata'],
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'jarvis = jarvis_sdk.jarvissdk:main'
        ]
    }
)
