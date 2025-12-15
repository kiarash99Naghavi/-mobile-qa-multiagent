"""
Setup script for mobile-qa-multiagent.
"""
from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="mobile-qa-multiagent",
    version="0.1.0",
    author="QualGent Team",
    description="Supervisor-Planner-Executor system for automated mobile app testing",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/mobile-qa-multiagent",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
    install_requires=[
        "google-genai>=0.1.0",
        "pyyaml>=6.0",
        "colorama>=0.4.6",
    ],
    entry_points={
        "console_scripts": [
            "mobileqa=mobileqa.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Testing",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
