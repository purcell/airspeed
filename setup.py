#!/usr/bin/env python

from setuptools import find_packages, setup


setup(
    name="airspeed-ext",
    version="0.6.0",
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
        "black",
        "deepdiff",
        "isort",
        "flake8",
        "flake8-black",
        "flake8-isort",
        "pytest==6.2.4",
        "pytest-httpserver",
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
