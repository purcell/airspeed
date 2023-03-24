#!/usr/bin/env python
# encoding: utf-8

import sys

from setuptools import find_packages, setup

if sys.version_info <= (2, 6):
    raise SystemExit("Python 2.6 or later is required.")


setup(
    name="airspeed-ext",
    version="0.5.19",
    description=(
        "Airspeed is a powerful and easy-to-use templating engine"
        " for Python that aims for a high level of compatibility "
        "with the popular Velocity library for Java."
    ),
    author="Steve Purcell, Chris Tarttelin, LocalStack Team",
    author_email="steve@pythonconsulting.com, chris@pythonconsulting.com, info@localstack.cloud",
    url="https://github.com/localstack/airspeed/",
    download_url="http://pypi.python.org/pypi/airspeed/",
    license="BSD",
    keywords="web.templating",
    install_requires=[
        "six",
        "cachetools",
    ],
    extras_require={"dev": [
        "black==22.3.0",
        "isort==5.12.0",
        "flake8>=6.0.0",
        "flake8-black>=0.3.6",
        "flake8-isort>=6.0.0",
    ]},
    test_suite="tests",
    tests_require=[],
    classifiers=[
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    packages=find_packages(exclude=["examples", "tests", "tests.*", "docs"]),
    include_package_data=False,
    zip_safe=True,
    entry_points={
        "web.templating": [
            "airspeed = airspeed.api:Airspeed",
        ]
    },
)
