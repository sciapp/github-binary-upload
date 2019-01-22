import os
import runpy
import subprocess
from setuptools import setup, find_packages


def get_version_from_pyfile(version_file="github_binary_upload.py"):
    file_globals = runpy.run_path(version_file)
    return file_globals["__version__"]


def get_install_requires_from_requirements(requirements_filename="requirements.txt"):
    try:
        with open(requirements_filename, "r", encoding="utf-8") as requirements_file:
            requirements = requirements_file.readlines()
    except OSError:
        import logging

        logging.warning("Could not read the requirements file.")
    return requirements


def get_long_description_from_readme(readme_filename="README.md"):
    rst_filename = "{}.rst".format(os.path.splitext(os.path.basename(readme_filename))[0])
    created_tmp_rst = False
    if not os.path.isfile(rst_filename):
        try:
            subprocess.check_call(["pandoc", readme_filename, "-t", "rst", "-o", rst_filename])
            created_tmp_rst = True
        except (OSError, subprocess.CalledProcessError):
            import logging

            logging.warning("Could not convert the readme file to rst.")
    long_description = None
    if os.path.isfile(rst_filename):
        with open(rst_filename, "r", encoding="utf-8") as readme_file:
            long_description = readme_file.read()
    if created_tmp_rst:
        os.remove(rst_filename)
    return long_description


version = get_version_from_pyfile()
long_description = get_long_description_from_readme()
install_requires = get_install_requires_from_requirements()

setup(
    name="github-binary-upload",
    version=version,
    py_modules=["github_binary_upload"],
    python_requires="~=3.3",
    install_requires=install_requires,
    entry_points={"console_scripts": ["github-binary-upload = github_binary_upload:main"]},
    author="Ingo Heimbach",
    author_email="i.heimbach@fz-juelich.de",
    description="github-binary-upload is a utility for publishing releases from tags with attached files on GitHub.",
    long_description=long_description,
    license="MIT",
    url="https://iffgit.fz-juelich.de/Scientific-IT-Systems/github-binary-upload",
    keywords=["git", "GitHub", "release", "assets"],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Version Control :: Git",
        "Topic :: Utilities",
    ],
)
