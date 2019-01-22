#!/usr/bin/env python3

import argparse
import getpass
import json
import logging
import os
import re
import subprocess
import sys
from typing import cast, Any, Callable, List, Optional  # noqa: F401  # pylint: disable=unused-import

try:
    # Allow an import of this module without `requests` being installed for meta data queries (e.g. version information)
    import requests
except ImportError:
    pass


__copyright__ = "Copyright © 2019 Forschungszentrum Jülich GmbH. All rights reserved."
__license__ = "MIT"
__version_info__ = (0, 1, 0)
__version__ = ".".join(map(str, __version_info__))


DEFAULT_GITHUB_ROOT = "github.com"
DEFAULT_CREDENTIALS_FILE = "~/.github-binary-uploadrc"


class MissingDependencyError(Exception):
    pass


class FileCommandError(Exception):
    pass


class InvalidFileCommandOutputError(Exception):
    pass


class NoTagsAvailableError(Exception):
    pass


class HTTPError(Exception):
    pass


class JSONError(Exception):
    pass


class InvalidUploadUrlError(Exception):
    pass


class InvalidServerNameError(Exception):
    pass


class CredentialsReadError(Exception):
    pass


class MissingTagError(Exception):
    pass


class TerminalColorCodes:
    BLACK = "\033[30;1m"
    RED = "\033[31;1m"
    GREEN = "\033[32;1m"
    YELLOW = "\033[33;1m"
    BLUE = "\033[34;1m"
    PURPLE = "\033[35;1m"
    CYAN = "\033[36;1m"
    GRAY = "\033[37;1m"
    LIGHT_BLACK = "\033[90;1m"
    BLINK = "\033[5m"
    RESET = "\033[0m"


class ColoredFormatter(logging.Formatter):
    _level_colors = {
        "DEBUG": TerminalColorCodes.GREEN,
        "INFO": TerminalColorCodes.BLUE,
        "WARNING": TerminalColorCodes.YELLOW,
        "ERROR": TerminalColorCodes.RED,
        "CRITICAL": TerminalColorCodes.RED + TerminalColorCodes.BLINK,
    }
    _name_color = TerminalColorCodes.LIGHT_BLACK

    def __init__(self, message_format: str):
        super().__init__(message_format)

    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        name = record.name
        if levelname in self._level_colors:
            record.levelname = "{}{}{}".format(self._level_colors[levelname], levelname, TerminalColorCodes.RESET)
        record.name = "{}{}{}".format(self._name_color, name, TerminalColorCodes.RESET)
        return logging.Formatter.format(self, record)


def has_terminal_color() -> bool:
    try:
        return os.isatty(sys.stderr.fileno()) and int(subprocess.check_output(["tput", "colors"])) >= 8
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def setup_colored_stderr_logging(logger: logging.Logger) -> None:  # pylint: disable=redefined-outer-name
    stream_handler = logging.StreamHandler()
    # stream_handler.setLevel(logger.level)
    if has_terminal_color():
        formatter = ColoredFormatter("%(levelname)s (%(name)s): %(message)s")  # type: logging.Formatter
    else:
        formatter = logging.Formatter("%(levelname)s (%(name)s): %(message)s")
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
setup_colored_stderr_logging(logger)


class AttributeDict(dict):  # type: ignore
    def __getattr__(self, attr: str) -> Any:
        return self[attr]

    def __setattr__(self, attr: str, value: Any) -> None:
        self[attr] = value


def get_mimetype(filepath: str) -> str:
    if not os.path.isfile(filepath):
        raise FileNotFoundError('The file "{}" does not exist or is not a regular file.'.format(filepath))
    if not os.access(filepath, os.R_OK):
        raise PermissionError('The file "{}" is not readable.'.format(filepath))
    try:
        file_command_output = subprocess.check_output(
            ["file", "--mime", filepath], universal_newlines=True
        )  # type: str
        mime_type = file_command_output.split()[1][:-1]
    except subprocess.CalledProcessError as e:
        raise FileCommandError("The `file` command returned with exit code {:d}".format(e.returncode))
    except IndexError:
        raise InvalidFileCommandOutputError(
            'The file command output "{}" could not be parsed.'.format(file_command_output)
        )
    return mime_type


def publish_release_from_tag(
    project: str,
    tag: Optional[str],
    assets: List[str],
    github_server: str,
    username: str,
    password: str,
    dry_run: bool = False,
) -> None:
    if "requests" not in sys.modules:
        raise MissingDependencyError('The "requests" package is missing. Please install and run again.')

    github_api_root_url = "https://api.{}".format(github_server)

    def fetch_latest_tag() -> str:
        try:
            tags_url = "{}/repos/{}/tags".format(github_api_root_url, project)
            response = requests.get(tags_url, auth=(username, password), headers={"Accept": "application/json"})
            response.raise_for_status()
            tags = response.json()
            if not tags:
                raise NoTagsAvailableError('The given repository "{}" has no tags yet.'.format(project))
            latest_tag = tags[0]["name"]  # type: str
            logger.info('Fetched the latest tag "%s" from the GitHub repository "%s"', latest_tag, project)
            return latest_tag
        except requests.HTTPError:
            raise HTTPError(
                'Could not query the latest tag of the repository "{}" due to a http error.'.format(project)
            )
        except (json.decoder.JSONDecodeError, IndexError):
            raise JSONError("Got an invalid json string.")
        except KeyError as e:
            raise JSONError('Got an unexpected json object missing the key "{}".'.format(e.args[0]))

    def publish_release(tag: str) -> str:
        def fetch_existing_release() -> Optional[str]:
            try:
                release_query_url = "{}/repos/{}/releases/tags/{}".format(github_api_root_url, project, tag)
                response = requests.get(
                    release_query_url, auth=(username, password), headers={"Accept": "application/json"}
                )
                response.raise_for_status()
                logger.info('Fetched the existing release "%s" in the GitHub repository "%s"', tag, project)
                asset_upload_url_with_get_params = response.json()["upload_url"]
                return asset_upload_url_with_get_params
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    return None
                raise HTTPError('Could not fetch the release "{}" due to a severe HTTP error.'.format(tag))

        def create_release() -> str:
            try:
                release_creation_url = "{}/repos/{}/releases".format(github_api_root_url, project)
                response = requests.post(
                    release_creation_url,
                    auth=(username, password),
                    json={"tag_name": tag, "name": tag, "body": "", "draft": False, "prerelease": False},
                )
                response.raise_for_status()
                logger.info('Created the release "%s" in the GitHub repository "%s"', tag, project)
                asset_upload_url_with_get_params = response.json()["upload_url"]
                return asset_upload_url_with_get_params
            except requests.HTTPError:
                raise HTTPError('Could not create the release "{}".'.format(tag))
            except json.decoder.JSONDecodeError:
                raise JSONError("Got an invalid json string.")
            except KeyError as e:
                raise JSONError('Got an unexpected json object missing the key "{}".'.format(e.args[0]))

        asset_upload_url_with_get_params = fetch_existing_release()
        if asset_upload_url_with_get_params is None:
            asset_upload_url_with_get_params = create_release()
        match_obj = re.match(r"([^{]+)(?:\{.*\})?", asset_upload_url_with_get_params)
        if not match_obj:
            raise InvalidUploadUrlError(
                'The upload url "{}" is not in the expected format.'.format(asset_upload_url_with_get_params)
            )
        asset_upload_url = match_obj.group(1)  # type: str
        return asset_upload_url

    def upload_asset(asset_upload_url: str, asset_filepath: str) -> None:
        asset_filename = os.path.basename(asset_filepath)
        try:
            asset_mimetype = get_mimetype(asset_filepath)
            with open(asset_filepath, "rb") as f:
                response = requests.post(
                    "{}?name={}".format(asset_upload_url, asset_filename),
                    auth=(username, password),
                    data=f,
                    headers={"Content-Type": asset_mimetype},
                )
            response.raise_for_status()
            logger.info(
                'Uploaded the asset "%s" attached to release "%s" of the GitHub repository "%s"',
                asset_filename,
                tag,
                project,
            )
        except requests.HTTPError:
            raise HTTPError('Could not upload the asset "{}".'.format(asset_filename))

    if tag is None:
        logger.info('No tag given, fetching the latest tag from the GitHub repository "%s"', project)
        tag = fetch_latest_tag()
    if dry_run:
        logger.info('Would create the release "%s" in the GitHub repository "%s"', tag, project)
    else:
        asset_upload_url = publish_release(tag)
    for asset_filepath in assets:
        if dry_run:
            logger.info(
                'Would upload the asset "%s" attached to release "%s" of the GitHub repository "%s"',
                os.path.basename(asset_filepath),
                tag,
                project,
            )
        else:
            upload_asset(asset_upload_url, asset_filepath)


def get_argumentparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
%(prog)s is a utility for publishing releases from tags with attached files on GitHub.
""",
    )
    parser.add_argument(
        "-g",
        "--github-server",
        action="store",
        dest="github_server",
        default=DEFAULT_GITHUB_ROOT,
        help="GitHub server hostname (default: %(default)s)",
    )
    parser.add_argument(
        "-c",
        "--credentials-file",
        action="store",
        dest="credentials_file",
        type=cast(Callable[[str], str], lambda x: os.path.abspath(os.path.expanduser(x))),
        default=DEFAULT_CREDENTIALS_FILE,
        help=(
            "path to a file containing username and password/access token "
            "(on two separate lines, default: %(default)s)"
        ),
    )
    parser.add_argument(
        "-l", "--latest", action="store_true", dest="latest_tag", help="get the latest tag from the GitHub API"
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", dest="dry_run", help="only print which releases would be published"
    )
    parser.add_argument(
        "-u", "--user", action="store", dest="username", help="user account for querying the GitHub API"
    )
    parser.add_argument(
        "-V", "--version", action="store_true", dest="print_version", help="print the version number and exit"
    )
    parser.add_argument("project", help='GitHub project in the format "<user>/<project name>"')
    parser.add_argument(
        "tag", nargs="?", help="tag that will be published as a release, ignored if '--latest' is given"
    )
    parser.add_argument("assets", nargs="*", help="files that will be attached to the release")
    return parser


def parse_arguments() -> AttributeDict:
    parser = get_argumentparser()
    args = AttributeDict({key: value for key, value in vars(parser.parse_args()).items()})
    if not args.print_version:
        match_obj = re.match(r"(?:[a-zA-Z]+://)?(.+)/?", args.github_server)
        if match_obj:
            args.github_server = match_obj.group(1)  # pylint: disable=attribute-defined-outside-init
        else:
            raise InvalidServerNameError("{} is not a valid server name.".format(args.github_server))
        if args.username is not None:
            if sys.stdin.isatty():
                args["password"] = getpass.getpass()
            else:
                args["password"] = sys.stdin.readline().rstrip()
        else:
            try:
                with open(args.credentials_file, "r") as f:
                    for key in ("username", "password"):
                        args[key] = f.readline().strip()
            except IOError:
                raise CredentialsReadError(
                    (
                        'Could not read credentials file "{f}". Either write "<username>\\n<access token>" to "{f}" or '
                        'use the "--user" option.'
                    ).format(f=args.credentials_file)
                )
        if not args.latest_tag and args.tag is None:
            raise MissingTagError("No tag is given.")
        if args.latest_tag and args.tag is not None:
            # In this case `args.tag` is part of the assets file list (but parsed wrongly)
            args.assets.insert(0, args.tag)
            args.tag = None  # pylint: disable=attribute-defined-outside-init
    return args


def main() -> None:
    expected_exceptions = (
        MissingDependencyError,
        OSError,
        FileCommandError,
        InvalidFileCommandOutputError,
        NoTagsAvailableError,
        HTTPError,
        JSONError,
        InvalidUploadUrlError,
        InvalidServerNameError,
        CredentialsReadError,
        MissingTagError,
    )
    try:
        args = parse_arguments()
        if args.print_version:
            print("{}, version {}".format(os.path.basename(sys.argv[0]), __version__))
        else:
            publish_release_from_tag(
                args.project, args.tag, args.assets, args.github_server, args.username, args.password, args.dry_run
            )
    except expected_exceptions as e:
        print("{}error{}: {}".format(TerminalColorCodes.RED, TerminalColorCodes.RESET, str(e)), file=sys.stderr)
        for i, exception_class in enumerate(expected_exceptions, start=3):
            if isinstance(e, exception_class):
                sys.exit(i)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()