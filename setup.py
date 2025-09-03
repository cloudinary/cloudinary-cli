#!/usr/bin/env python3

import setuptools

with open("README.md", "r") as rmf:
    long_description = rmf.read()

with open('cloudinary_cli/version.py') as vf:
    version = vf.readline().strip().split('"')[1]

with open('requirements.txt') as rqf:
    requirements = rqf.read().splitlines()

setuptools.setup(
    name="cloudinary-cli",
    version=version,
    author="Cloudinary, Brian Luk",
    author_email="info@cloudinary.com, lukitsbrian@gmail.com",
    classifiers=[
        "Programming Language :: Python :: 3 :: Only",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    description="A command line interface for Cloudinary with full API support",
    entry_points={
        'console_scripts': [
            'cld=cloudinary_cli.cli:main',
            'cloudinary=cloudinary_cli.cli:main',
        ],
    },
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/cloudinary/cloudinary-cli",
    packages=setuptools.find_packages(),
    keywords='cloudinary cli pycloudinary image video digital asset management command line interface transformation '
             'friendly easy flexible',
    license="MIT",
    python_requires='>=3.6.0',
    setup_requires=["pytest-runner"],
    tests_require=["pytest", "mock", "urllib3"],
    install_requires=requirements,
    include_package_data=True,
    zip_safe=False
)
