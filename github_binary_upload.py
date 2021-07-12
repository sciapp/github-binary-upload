#!/usr/bin/env python3

import argparse
import collections
import getpass
import json
import logging
import os
import re
import subprocess
import sys
from typing import Any, Callable, List, Optional, cast  # noqa: F401  # pylint: disable=unused-import

try:
    # Allow an import of this module without `requests` and `yacl` being installed for meta data queries
    # (e.g. version information)
    import requests
    from yacl import setup_colored_stderr_logging
except ImportError:
    pass


__copyright__ = "Copyright © 2019 Forschungszentrum Jülich GmbH. All rights reserved."
__license__ = "MIT"
__version_info__ = (0, 1, 9)
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


class MissingProjectError(Exception):
    pass


class MissingTagError(Exception):
    pass


class CredentialsReadError(Exception):
    pass


logger = logging.getLogger(__name__)


class AttributeDict(dict):  # type: ignore
    def __getattr__(self, attr: str) -> Any:
        return self[attr]

    def __setattr__(self, attr: str, value: Any) -> None:
        self[attr] = value


Release = collections.namedtuple("Release", ["id", "asset_upload_url"])
Asset = collections.namedtuple("Asset", ["id", "name"])


def setup_stderr_logging() -> None:
    logging.basicConfig(level=logging.INFO)
    setup_colored_stderr_logging(format_string="[%(levelname)s] %(message)s")


def get_mimetype(filepath: str) -> str:
    if not os.path.isfile(filepath):
        raise FileNotFoundError('The file "{}" does not exist or is not a regular file.'.format(filepath))
    if not os.access(filepath, os.R_OK):
        raise PermissionError('The file "{}" is not readable.'.format(filepath))

    if os.name == "nt":
        try:
            import mimetypes

            mime_type = mimetypes.types_map["." + filepath.split(".")[-1]]
        except ModuleNotFoundError:
            raise Exception("mimetypes module not found. Do something like pip install mimetypes")
    else:
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
    asset_filepaths: List[str],
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

    def publish_release(tag: str) -> Release:
        def strip_asset_upload_url(asset_upload_url_with_get_params: str) -> str:
            match_obj = re.match(r"([^{]+)(?:\{.*\})?", asset_upload_url_with_get_params)
            if not match_obj:
                raise InvalidUploadUrlError(
                    'The upload url "{}" is not in the expected format.'.format(asset_upload_url_with_get_params)
                )
            asset_upload_url = match_obj.group(1)  # type: str
            return asset_upload_url

        def fetch_existing_release() -> Optional[Release]:
            try:
                release_query_url = "{}/repos/{}/releases/tags/{}".format(github_api_root_url, project, tag)
                response = requests.get(
                    release_query_url, auth=(username, password), headers={"Accept": "application/json"}
                )
                response.raise_for_status()
                logger.info('Fetched the existing release "%s" in the GitHub repository "%s"', tag, project)
                response_json = response.json()
                asset_upload_url_with_get_params = response_json["upload_url"]
                asset_upload_url = strip_asset_upload_url(asset_upload_url_with_get_params)
                release = Release(response_json["id"], asset_upload_url)
                return release
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    return None
                raise HTTPError('Could not fetch the release "{}" due to a severe HTTP error.'.format(tag))

        def create_release() -> Release:
            try:
                release_creation_url = "{}/repos/{}/releases".format(github_api_root_url, project)
                response = requests.post(
                    release_creation_url,
                    auth=(username, password),
                    json={"tag_name": tag, "name": tag, "body": "", "draft": False, "prerelease": False},
                )
                response.raise_for_status()
                logger.info('Created the release "%s" in the GitHub repository "%s"', tag, project)
                response_json = response.json()
                asset_upload_url_with_get_params = response_json["upload_url"]
                asset_upload_url = strip_asset_upload_url(asset_upload_url_with_get_params)
                release = Release(response_json["id"], asset_upload_url)
                return release
            except requests.HTTPError:
                raise HTTPError('Could not create the release "{}".'.format(tag))
            except json.decoder.JSONDecodeError:
                raise JSONError("Got an invalid json string.")
            except KeyError as e:
                raise JSONError('Got an unexpected json object missing the key "{}".'.format(e.args[0]))

        release = fetch_existing_release()
        if release is None:
            release = create_release()
        return release

    def list_assets(release: Release) -> List[Asset]:
        try:
            asset_list_url = "{}/repos/{}/releases/{}/assets".format(github_api_root_url, project, release.id)
            response = requests.get(asset_list_url, auth=(username, password))
            response.raise_for_status()
            assets = [Asset(asset_dict["id"], asset_dict["name"]) for asset_dict in response.json()]
            return assets
        except requests.HTTPError:
            raise HTTPError('Could not get a list of assets for project "{}".'.format(project))
        except json.decoder.JSONDecodeError:
            raise JSONError("Got an invalid json string.")
        except KeyError as e:
            raise JSONError('Got an unexpected json object missing the key "{}".'.format(e.args[0]))

    def delete_asset(asset: Asset) -> None:
        try:
            asset_delete_url = "{}/repos/{}/releases/assets/{}".format(github_api_root_url, project, asset.id)
            response = requests.delete(asset_delete_url, auth=(username, password))
            response.raise_for_status()
            logger.info(
                'Deleted the asset "%s" attached to release "%s" of the GitHub repository "%s"',
                asset.name,
                tag,
                project,
            )
        except requests.HTTPError:
            raise HTTPError('Could not get a list of assets for project "{}".'.format(project))
        except json.decoder.JSONDecodeError:
            raise JSONError("Got an invalid json string.")
        except KeyError as e:
            raise JSONError('Got an unexpected json object missing the key "{}".'.format(e.args[0]))

    def upload_asset(release: Release, asset_filepath: str) -> None:
        asset_filename = os.path.basename(asset_filepath)
        try:
            asset_mimetype = get_mimetype(asset_filepath)
            with open(asset_filepath, "rb") as f:
                response = requests.post(
                    "{}?name={}".format(release.asset_upload_url, asset_filename),
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
        assets = []  # type: List[Asset]
    else:
        release = publish_release(tag)
        assets = list_assets(release)
    for asset_filepath in asset_filepaths:
        asset_matches = [asset for asset in assets if asset.name == os.path.basename(asset_filepath)]
        if dry_run:
            for asset_match in asset_matches:
                logger.info(
                    'Would delete the asset "%s" attached to release "%s" of the GitHub repository "%s"',
                    asset_match.name,
                    tag,
                    project,
                )
            logger.info(
                'Would upload the asset "%s" attached to release "%s" of the GitHub repository "%s"',
                os.path.basename(asset_filepath),
                tag,
                project,
            )
        else:
            for asset_match in asset_matches:
                delete_asset(asset_match)
            upload_asset(release, asset_filepath)


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
        "-u",
        "--user",
        action="store",
        dest="username",
        help="user account for querying the GitHub API; the password is read from stdin",
    )
    parser.add_argument(
        "-V", "--version", action="store_true", dest="print_version", help="print the version number and exit"
    )
    parser.add_argument("project", nargs="?", help='GitHub project in the format "<user>/<project name>"')
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
        if args.project is None:
            raise MissingProjectError("No project is given.")
        if not args.latest_tag and args.tag is None:
            raise MissingTagError("No tag is given.")
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
        MissingProjectError,
        MissingTagError,
        CredentialsReadError,
    )
    setup_stderr_logging()
    try:
        args = parse_arguments()
        if args.print_version:
            print("{}, version {}".format(os.path.basename(sys.argv[0]), __version__))
        else:
            publish_release_from_tag(
                args.project, args.tag, args.assets, args.github_server, args.username, args.password, args.dry_run
            )
    except expected_exceptions as e:
        logger.error(str(e))
        for i, exception_class in enumerate(expected_exceptions, start=3):
            if isinstance(e, exception_class):
                sys.exit(i)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
