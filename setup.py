from setuptools import setup
import pathlib

here = pathlib.Path(__file__).parent.resolve()

long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="extension",
    version="1.3.8",
    description="A AWS Mainframe Modernization and Stonebranch working extension example",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/aws-samples/aws-mainframe-modernization-stonebranch-integration",
    author="Vaidyanathan GanesaSankaran",
    author_email="vaidysan@amazon.com",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Stonebranch Extensions",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3 :: Only",
    ],
    keywords="extension, setuptools, stonebranch, aws-m2",
    packages={".": "src"},
    package_dir={".": "src"},
    python_requires=">=3.7, <4",
    package_data={
        ".": ["extension.yml"],
    },
    zip_safe=True,
    project_urls={
        "Source": "https://github.com/aws-samples/aws-mainframe-modernization-stonebranch-integration",
    },
)
