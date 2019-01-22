# GitHub Binary Upload

## Introduction

`github-binary-upload` is a script for creating GitHub releases from Git tags with attached assets.

## Installation

Install with `pip` directly from source:

```bash
python3 -m pip install git+https://iffgit.fz-juelich.de/Scientific-IT-Systems/github-binary-upload.git
```

## Usage

After installation you can run `github-binary-upload`:

```
usage: github-binary-upload [-h] [-g GITHUB_SERVER] [-c CREDENTIALS_FILE]
                            [-l] [-n] [-u USERNAME] [-V]
                            project [tag] [assets [assets ...]]

github-binary-upload is a utility for publishing releases from tags with attached files on GitHub.

positional arguments:
  project               GitHub project in the format "<user>/<project name>"
  tag                   tag that will be published as a release, ignored if '
                        --latest' is given
  assets                files that will be attached to the release

optional arguments:
  -h, --help            show this help message and exit
  -g GITHUB_SERVER, --github-server GITHUB_SERVER
                        GitHub server hostname (default: github.com)
  -c CREDENTIALS_FILE, --credentials-file CREDENTIALS_FILE
                        path to a file containing username and password/access
                        token (on two separate lines, default: ~/.github-
                        binary-uploadrc)
  -l, --latest          get the latest tag from the GitHub API
  -n, --dry-run         only print which releases would be published
  -u USERNAME, --user USERNAME
                        user account for querying the GitHub API
  -V, --version         print the version number and exit
```

### Example

Run

```bash
github-binary-upload -u ExampleUser -l ExampleUser/ExampleProjet MyFirstAsset.zip MySecondAsset.whl
```

to create a release from the latest tag in the GitHub project `ExampleUser/ExampleProjet`. The files `MyFirstAsset.zip`
and `MySecondAsset.whl` will be attached as downloadable files.
