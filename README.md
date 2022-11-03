# GitHub Binary Upload

## Introduction

`github-binary-upload` is a script for creating GitHub releases from Git tags with attached assets.

## Installation

As a prerequisite, `apt install file`.
- From PyPI:

  ```bash
  python3 -m pip install github-binary-upload
  ```

- Self-contained executables for Linux x86_64 with glibc >= 2.17 (any recent Linux distribution) and macOS High Sierra
  and newer are available on the [releases page](https://github.com/sciapp/github-binary-upload/releases/latest).
- AUR package for Arch Linux users:
  [python-github-binary-upload](https://aur.archlinux.org/packages/python-github-binary-upload/)

## Usage

After installation you can run `github-binary-upload`:

```text
usage: github-binary-upload [-h] [-g GITHUB_SERVER] [-c CREDENTIALS_FILE] [-l]
                            [-n] [-u USERNAME] [-V]
                            [project] [tag] [assets [assets ...]]

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
                        user account for querying the GitHub API; the password
                        is read from stdin
  -V, --version         print the version number and exit
```

### Example

Run

```bash
github-binary-upload -u ExampleUser -l ExampleUser/ExampleProject MyFirstAsset.zip MySecondAsset.whl
```

to create a release from the latest tag in the GitHub project `ExampleUser/ExampleProject`. The files `MyFirstAsset.zip`
and `MySecondAsset.whl` will be attached as downloadable files.

`github-binary-upload` can be called multiple times on the same tag. The release will be recreated each time. This is
especially useful to CI pipelines which can run more than once.

### Python API

`github-binary-upload` defines a function `publish_release_from_tag` which can be called from Python code:

```python
from github_binary_upload import publish_release_from_tag


publish_release_from_tag(
    project, tag, assets, github_server, username, password, dry_run
)
```

If `tag` is `None`, the latest tag will be converted to a GitHub release. `dry_run` is an optional parameter which
defaults to `False`.

## Contributing

Please open [an issue on GitHub](https://github.com/sciapp/github-binary-upload/issues/new) if you experience bugs or
miss features. Please consider to send a pull request if you can spend time on fixing the issue yourself. This project
uses [pre-commit](https://pre-commit.com) to ensure code quality and a consistent code style. Run

```bash
make git-hooks-install
```

to install all linters as Git hooks in your local clone of `github-binary-upload`.
