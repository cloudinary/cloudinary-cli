import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="cloudinary-cli",
    version="0.1.0",
    author="Brian Luk",
    author_email="brian@cloudinary.com",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    description="A command line interface for Cloudinary with full API support",
    entry_points={
        'console_scripts': ['cld=cloudinary_cli.cli:main'],
    },
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/brian-cloudinary/cloudinary-cli",
    packages=setuptools.find_packages(),
    keywords='cloudinary cli pycloudinary image video digital asset management command line interface transformation friendly easy flexible',
    license="MIT",
    install_requires=[
        "cloudinary",
        "pygments",
        "jinja2",
        "click"
    ],
    include_package_data=True,
    zip_safe=False
)