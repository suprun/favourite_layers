"""Build and upload the plugin to the official QGIS plugin repository."""

import argparse
import configparser
import json
import os
import re
import tempfile
import subprocess
import sys
import uuid
import xmlrpc.client
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_ARCHIVE = REPOSITORY_DIR / "favourite_layers.zip"
REST_API_URL = (
    "https://plugins.qgis.org/plugins/{package_name}/version/add/api/"
)
XMLRPC_API_URL = "https://{username}:{password}@plugins.qgis.org/plugins/RPC2/"
MAX_PACKAGE_SIZE = 25 * 1024 * 1024
PACKAGE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class PublishError(Exception):
    """Raised when the package cannot be validated or uploaded."""


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Build and upload Favourite Layers to the official QGIS plugin "
            "repository. Values from the process environment override .env."
        ),
        epilog=(
            "Authentication: set QGIS_PLUGIN_TOKEN, or set OSGEO_USERNAME "
            "and OSGEO_PASSWORD. Optional: QGIS_PLUGIN_AUTO_APPROVE=true."
        ),
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="Path to the environment file (default: project .env).",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=DEFAULT_ARCHIVE,
        help="Plugin ZIP path (default: repo/favourite_layers.zip).",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Upload the existing archive without running repo/restore.py.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate the package without uploading it.",
    )
    approval_group = parser.add_mutually_exclusive_group()
    approval_group.add_argument(
        "--auto-approve",
        action="store_true",
        dest="auto_approve",
        help="Request publication after a successful security scan.",
    )
    approval_group.add_argument(
        "--no-auto-approve",
        action="store_false",
        dest="auto_approve",
        help="Keep the normal manual approval flow.",
    )
    parser.set_defaults(auto_approve=None)
    return parser.parse_args()


def load_env_file(path):
    if not path.exists():
        return {}

    values = {}
    with path.open("r", encoding="utf-8-sig") as env_file:
        for line_number, raw_line in enumerate(env_file, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                raise PublishError(
                    f"Invalid entry in {path} at line {line_number}."
                )

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise PublishError(
                    f"Invalid variable name in {path} at line {line_number}."
                )
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            elif " #" in value:
                value = value.split(" #", 1)[0].rstrip()
            values[key] = value
    return values


def get_setting(env_values, *names):
    for name in names:
        if name in os.environ:
            return os.environ[name]
        if name in env_values:
            return env_values[name]
    return None


def parse_boolean(value, variable_name):
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise PublishError(
        f"{variable_name} must be true/false, yes/no, on/off, or 1/0."
    )


def build_package():
    restore_script = REPOSITORY_DIR / "restore.py"
    if not restore_script.is_file():
        raise PublishError(f"Build script not found: {restore_script}")

    print("Building the plugin package with repo/restore.py...", flush=True)
    try:
        subprocess.run(
            [sys.executable, str(restore_script)],
            cwd=PROJECT_ROOT,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise PublishError(
            f"Package build failed with exit code {error.returncode}."
        ) from error


def is_forbidden_package_entry(file_name):
    path_parts = file_name.replace("\\", "/").split("/")
    return any(
        part == ".env"
        or part.startswith(".env.")
        or part in {".git", "__pycache__"}
        or part.endswith(".pyc")
        for part in path_parts
    )


def sanitize_package(archive_path):
    if not archive_path.is_file():
        raise PublishError(f"Plugin package not found: {archive_path}")

    temporary_path = None
    removed_entries = []
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f"{archive_path.stem}-",
            suffix=".tmp",
            dir=archive_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        with zipfile.ZipFile(archive_path) as source_archive:
            with zipfile.ZipFile(temporary_path, "w") as clean_archive:
                for entry in source_archive.infolist():
                    if is_forbidden_package_entry(entry.filename):
                        removed_entries.append(entry.filename)
                        continue
                    clean_archive.writestr(entry, source_archive.read(entry))
        os.replace(temporary_path, archive_path)
    except (OSError, zipfile.BadZipFile) as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise PublishError(f"Cannot sanitize plugin package: {error}") from error

    if removed_entries:
        print("Removed unsafe package entries:")
        for entry_name in removed_entries:
            print(f"  - {entry_name}")


def read_package_metadata(archive_path):
    if not archive_path.is_file():
        raise PublishError(f"Plugin package not found: {archive_path}")
    if archive_path.stat().st_size > MAX_PACKAGE_SIZE:
        raise PublishError("Plugin package exceeds the QGIS 25 MB limit.")

    try:
        with zipfile.ZipFile(archive_path) as archive:
            damaged_file = archive.testzip()
            if damaged_file:
                raise PublishError(
                    f"Plugin package contains a damaged file: {damaged_file}"
                )

            file_names = [
                name for name in archive.namelist() if name and not name.endswith("/")
            ]
            forbidden_entries = [
                name for name in file_names if is_forbidden_package_entry(name)
            ]
            if forbidden_entries:
                raise PublishError(
                    "Plugin package contains forbidden secret or temporary files. "
                    "Rebuild it without --skip-build."
                )
            roots = {name.split("/", 1)[0] for name in file_names}
            if len(roots) != 1:
                raise PublishError(
                    "Plugin package must contain exactly one top-level directory."
                )

            package_name = roots.pop()
            if not PACKAGE_NAME_PATTERN.fullmatch(package_name):
                raise PublishError(
                    "The top-level plugin directory has an invalid package name."
                )

            metadata_name = f"{package_name}/metadata.txt"
            if metadata_name not in file_names:
                raise PublishError(
                    f"Plugin package does not contain {metadata_name}."
                )
            metadata_text = archive.read(metadata_name).decode("utf-8-sig")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise PublishError(f"Cannot read plugin package: {error}") from error

    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(metadata_text)
        version = parser.get("general", "version").strip()
    except (configparser.Error, configparser.NoOptionError) as error:
        raise PublishError(
            "Plugin metadata does not contain a valid version."
        ) from error
    if not version:
        raise PublishError("Plugin metadata version cannot be empty.")
    return package_name, version


def read_project_version():
    metadata_path = PROJECT_ROOT / "metadata.txt"
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        with metadata_path.open("r", encoding="utf-8-sig") as metadata_file:
            parser.read_file(metadata_file)
        version = parser.get("general", "version").strip()
    except (OSError, configparser.Error) as error:
        raise PublishError(f"Cannot read {metadata_path}.") from error
    if not version:
        raise PublishError("Project metadata version cannot be empty.")
    return version


def create_multipart_body(archive_path, auto_approve):
    boundary = f"----qgis-plugin-{uuid.uuid4().hex}"
    archive_content = archive_path.read_bytes()
    parts = [
        f"--{boundary}\r\n".encode("ascii"),
        (
            'Content-Disposition: form-data; name="package"; '
            f'filename="{archive_path.name}"\r\n'
        ).encode("utf-8"),
        b"Content-Type: application/zip\r\n\r\n",
        archive_content,
        b"\r\n",
        f"--{boundary}\r\n".encode("ascii"),
        b'Content-Disposition: form-data; name="auto_approve_after_scan"\r\n\r\n',
        b"true" if auto_approve else b"false",
        b"\r\n",
        f"--{boundary}--\r\n".encode("ascii"),
    ]
    return boundary, b"".join(parts)


def upload_with_token(archive_path, package_name, token, auto_approve):
    boundary, request_body = create_multipart_body(archive_path, auto_approve)
    request = Request(
        REST_API_URL.format(package_name=quote(package_name, safe="")),
        data=request_body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urlopen(request, timeout=120) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            status = response.status
    except HTTPError as error:
        response_body = error.read(8192).decode("utf-8", errors="replace").strip()
        details = f": {response_body}" if response_body else ""
        raise PublishError(
            f"QGIS repository returned HTTP {error.code}{details}"
        ) from error
    except URLError as error:
        raise PublishError(
            f"Cannot reach the QGIS repository: {error.reason}"
        ) from error

    print(f"Upload accepted by the REST API (HTTP {status}).")
    if response_body:
        try:
            response_data = json.loads(response_body)
        except json.JSONDecodeError:
            return
        if isinstance(response_data, dict):
            plugin_id = response_data.get("plugin_id") or response_data.get("plugin")
            version_id = response_data.get("version_id") or response_data.get("id")
            if plugin_id is not None:
                print(f"Plugin ID: {plugin_id}")
            if version_id is not None:
                print(f"Version ID: {version_id}")


def upload_with_osgeo_credentials(
    archive_path, username, password, auto_approve
):
    endpoint = XMLRPC_API_URL.format(
        username=quote(username, safe=""),
        password=quote(password, safe=""),
    )
    server = xmlrpc.client.ServerProxy(
        endpoint,
        allow_none=True,
        use_builtin_types=True,
    )
    try:
        with archive_path.open("rb") as archive_file:
            result = server.plugin.upload(
                xmlrpc.client.Binary(archive_file.read()),
                auto_approve,
            )
    except xmlrpc.client.Fault as error:
        raise PublishError(
            f"QGIS repository rejected the upload: {error.faultString}"
        ) from error
    except xmlrpc.client.ProtocolError as error:
        raise PublishError(
            f"QGIS repository returned HTTP {error.errcode}: {error.errmsg}"
        ) from error
    except OSError as error:
        raise PublishError("Cannot reach the QGIS repository.") from error

    print("Upload accepted by the XML-RPC API.")
    if isinstance(result, (list, tuple)) and len(result) >= 2:
        print(f"Plugin ID: {result[0]}")
        print(f"Version ID: {result[1]}")


def get_authentication(env_values):
    token = get_setting(
        env_values,
        "QGIS_PLUGIN_TOKEN",
        "QGIS_PLUGIN_REPOSITORY_TOKEN",
    )
    if token:
        return "token", token, None

    username = get_setting(
        env_values,
        "OSGEO_USERNAME",
        "OSGEO_USER",
        "QGIS_PLUGIN_REPOSITORY_USERNAME",
        "QGIS_PLUGIN_REPO_USERNAME",
        "QGIS_USERNAME",
    )
    password = get_setting(
        env_values,
        "OSGEO_PASSWORD",
        "QGIS_PLUGIN_REPOSITORY_PASSWORD",
        "QGIS_PLUGIN_REPO_PASSWORD",
        "QGIS_PASSWORD",
    )
    if username and password:
        return "osgeo", username, password
    if username or password:
        raise PublishError(
            "Both OSGEO_USERNAME and OSGEO_PASSWORD must be configured."
        )
    raise PublishError(
        "Set QGIS_PLUGIN_TOKEN, or OSGEO_USERNAME and OSGEO_PASSWORD in .env."
    )


def main():
    arguments = parse_arguments()
    env_values = load_env_file(arguments.env_file.resolve())

    if not arguments.skip_build:
        if arguments.archive.resolve() != DEFAULT_ARCHIVE.resolve():
            raise PublishError("--archive can only be used with --skip-build.")
        build_package()

    archive_path = arguments.archive.resolve()
    if not arguments.skip_build:
        sanitize_package(archive_path)
    package_name, version = read_package_metadata(archive_path)
    project_version = read_project_version()
    if version != project_version:
        raise PublishError(
            f"Package version {version} does not match project version "
            f"{project_version}. Rebuild the package first."
        )
    print(f"Package: {archive_path}")
    print(f"Plugin: {package_name}")
    print(f"Version: {version}")

    if arguments.auto_approve is None:
        auto_approve_value = get_setting(
            env_values, "QGIS_PLUGIN_AUTO_APPROVE"
        )
        auto_approve = (
            parse_boolean(auto_approve_value, "QGIS_PLUGIN_AUTO_APPROVE")
            if auto_approve_value is not None
            else False
        )
    else:
        auto_approve = arguments.auto_approve
    print(f"Auto-approve after security scan: {'yes' if auto_approve else 'no'}")

    if arguments.dry_run:
        print("Dry run completed. Nothing was uploaded.")
        return 0

    auth_type, first_secret, second_secret = get_authentication(env_values)
    if auth_type == "token":
        upload_with_token(
            archive_path,
            package_name,
            first_secret,
            auto_approve,
        )
    else:
        upload_with_osgeo_credentials(
            archive_path,
            first_secret,
            second_secret,
            auto_approve,
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PublishError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
