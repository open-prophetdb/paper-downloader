#!/usr/bin/env python

"""The setup script."""

from setuptools import setup, find_packages

with open("README.md") as readme_file:
    readme = readme_file.read()

with open("HISTORY.rst") as history_file:
    history = history_file.read()

with open("./requirements.txt") as f:
    all_requirements = f.read().splitlines()
    requirements = [x for x in all_requirements if not x.startswith("git+https")]

test_requirements = []

setup(
    author="Jingcheng Yang",
    author_email="yjcyxky@163.com",
    python_requires=">=3.6",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    description="It is a tool for fetching metadata of papers and downloading related pdf files.",
    entry_points={
        "console_scripts": [
            "pfetcher=paper_downloader.cli:cli",
            "pfetcher-monitor=paper_downloader.monitor:cli",
            "pfetcher-syncer=paper_downloader.syncer:cli",
            "pdownloader=paper_downloader.cli:cli",
            "pdownloader-monitor=paper_downloader.monitor:cli",
            "pdownloader-syncer=paper_downloader.syncer:cli",
        ],
    },
    install_requires=requirements + ["metapub @ git+https://github.com/yjcyxky/metapub.git@master"],
    license="MIT license",
    long_description=readme + "\n\n" + history,
    include_package_data=True,
    keywords="Paper Downloader",
    name="paper-downloader",
    packages=find_packages(include=["paper_downloader", "paper_downloader.*"]),
    test_suite="tests",
    tests_require=test_requirements,
    url="https://github.com/yjcyxky/paper-downloader",
    version="0.1.0",
    zip_safe=False,
)
