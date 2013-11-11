#!/usr/bin/env python
# encoding: utf-8

import sys

from setuptools import setup, find_packages


if sys.version_info <= (2, 1):
    raise SystemExit("Python 2.1 or later is required.")



setup(
        name = "airspeed",
        version = "0.4.2",

        description = "Airspeed is a powerful and easy-to-use templating engine for Python that aims for a high level of compatibility with the popular Velocity library for Java.",
        author = "Steve Purcell and Chris Tarttelin",
        author_email = "steve@pythonconsulting.com, chris@pythonconsulting.com",
        url = "http://dev.sanityinc.com/airspeed/wiki",
        download_url = "http://pypi.python.org/pypi/airspeed/",
        license = "BSD",
        keywords = 'web.templating',

        test_suite = 'nose.collector',
        tests_require = ['nose', 'coverage'],

        classifiers = [
                "Environment :: Web Environment",
                "Intended Audience :: Developers",
                "License :: OSI Approved :: BSD License",
                "Operating System :: OS Independent",
                "Programming Language :: Python",
                "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
                "Topic :: Software Development :: Libraries :: Python Modules"
            ],

        packages = find_packages(exclude=['examples', 'tests', 'tests.*', 'docs']),
        include_package_data = False,
        zip_safe = True,

        entry_points = {
                'web.templating': [
                        'airspeed = airspeed.api:Airspeed',
                ]
            }
    )
