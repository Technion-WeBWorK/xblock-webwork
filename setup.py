"""Setup for WeBWorK XBlock."""

import os
from setuptools import setup


def package_data(pkg, roots):
    """Generic function to find package_data.

    All of the files under each of the `roots` will be declared as package
    data for package `pkg`.

    """
    data = []
    for root in roots:
        for dirname, _, files in os.walk(os.path.join(pkg, root)):
            for fname in files:
                data.append(os.path.relpath(os.path.join(dirname, fname), pkg))

    return {pkg: data}


def load_requirements(*requirements_paths):
    """
    Load all requirements from the specified requirements files.
    Returns a list of requirement strings.
    """
    requirements = set()
    for path in requirements_paths:
        with open(path) as reqs:
            requirements.update(
                line.split('#')[0].strip() for line in reqs
                if is_requirement(line.strip())
            )
    return list(requirements)


def is_requirement(line):
    """
    Return True if the requirement line is a package requirement;
    that is, it is not blank, a comment, a URL, or an included file.
    """
    return line and not line.startswith(('-r', '#', '-e', 'git+', '-c'))


setup(
    name='webwork-xblock',
    version='0.0.9', # This branch is for Ginkgo (python 2.7) and is being called version 0.0.9
    description='WeBWorK XBlock - supports embedding WeBWorK problems in edX courses',
    license='Affero GNU General Public License v3 (AGPL)',
    url='https://github.com/Technion-WeBWorK/xblock-webwork',
    classifiers=[
        'Classifier: Development Status ::  - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Framework :: Django',
        'Framework :: Django :: 2.2',
    ],
    packages=[
        'webwork',
    ],
    install_requires=load_requirements('requirements/base.in'),
    entry_points={
        'xblock.v1': [
            'webwork = webwork:WeBWorKXBlock',
        ]
    },
    package_data=package_data("webwork", ["static", "public", "translations"]),
)
