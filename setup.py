
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
"""Setup file to be able to build a deb package."""

from setuptools import setup, find_packages


def read_requirements(file: str = "requirements.txt") -> list[str]:
    """Get the requirements of the project.

    Args:
        file (str, optional): Path to the requirements. Defaults to "requirements.txt".

    Returns:
        list[str]: requirements of the project
    """
    with open(file) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


setup(
    name="prometheus-opensearch-dashboards-exporter",
    version="0.1.0",
    description="An exporter for OpenSearch Dashboards",
    author="Gabriel Cocenza",
    author_email="gabriel.cocenza@canonical.com",
    license="Apache License",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    python_requires=">=3.10",
    packages=find_packages(where="src"),
    include_package_data=True,
    install_requires=read_requirements(),
    entry_points={
        "console_scripts": [
            "prometheus-opensearch-dashboards-exporter=prometheus_opensearch_dashboards_exporter.main:main"
        ],
    },
    package_dir={"": "src"},
)
