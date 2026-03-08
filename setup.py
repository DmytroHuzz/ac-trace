from setuptools import find_packages, setup


setup(
    packages=find_packages(include=["ac_trace", "ac_trace.*", "demo", "demo.*"]),
)
