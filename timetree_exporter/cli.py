"""CLI helpers for timetree_exporter."""

import argparse
import logging
import os
import re
import subprocess
from pathlib import Path

from timetree_exporter import __version__
from timetree_exporter.config import (
    DEVELOPER_MODE_ENV,
    RAW_OUTPUT_DIR,
    resolve_raw_output_dir,
)
from timetree_exporter.utils import safe_getpass

package_logger = logging.getLogger(__package__)

__all__ = [
    "DEVELOPER_MODE_ENV",
    "RAW_OUTPUT_DIR",
    "configure_logging",
    "list_labels_and_exit",
    "parse_args",
    "raw_output_dir",
    "resolve_email",
    "resolve_password",
]


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Convert Timetree events to iCal format",
        prog="timetree_exporter",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Path to the output iCal file",
        default=str(Path.cwd() / "timetree.ics"),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Increase output verbosity",
        action="store_true",
    )
    parser.add_argument(
        "-e",
        "--email",
        type=str,
        help="Email address",
        default=None,
    )
    parser.add_argument(
        "-c",
        "--calendar_code",
        type=str,
        help="The Calendar Code you want to export, or public calendar id with --public-calendar",
        default=None,
    )
    parser.add_argument(
        "--public-calendar",
        help="Export a public calendar by id without signing in",
        action="store_true",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--list-labels",
        help="List labels for the selected calendar and exit",
        action="store_true",
    )
    parser.add_argument(
        "--split-by-label",
        help="Export events into separate .ics files grouped by label",
        action="store_true",
    )
    parser.add_argument(
        "--include-comments",
        help=(
            "Export private event comments. This makes one or more extra TimeTree requests "
            "per event and may take much longer or trigger rate limits."
        ),
        action="store_true",
    )
    parser.add_argument(
        "--include-images",
        help=(
            "Export images attached to private event activities. This makes extra TimeTree "
            "requests per event and may take much longer."
        ),
        action="store_true",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        help="Number of concurrent threads for fetching comments (default: 10)",
        default=10,
    )
    parser.add_argument(
        "--developer-mode",
        help=(
            "Enable developer diagnostics, including raw TimeTree API response output "
            f"(or set {DEVELOPER_MODE_ENV}=1)"
        ),
        action="store_true",
    )
    parser.add_argument(
        "--raw-output-dir",
        type=str,
        help="Directory for developer-mode raw TimeTree API JSON responses",
        default=None,
    )
    return parser.parse_args()


def resolve_email(cli_email):
    """Resolve email from CLI arg, env var, or prompt."""
    if cli_email:
        return cli_email
    env_email = os.environ.get("TIMETREE_EMAIL")
    if env_email:
        return env_email
    return input("Enter your email address: ")


def _read_password_file(path):
    """Read a password file, refusing files readable by group or others."""
    file_path = Path(path).expanduser()
    mode = file_path.stat().st_mode
    if mode & 0o077:
        raise PermissionError(
            f"{file_path} must not be accessible by group/others (run: chmod 600 {file_path})"
        )
    return file_path.read_text(encoding="utf-8").strip()


def _read_keychain_password(service, account):
    """Read a password from the macOS Keychain without a shell."""
    command = ["/usr/bin/security", "find-generic-password", "-s", service, "-w"]
    if account:
        command[3:3] = ["-a", account]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"Keychain item not found for service {service!r}")
    return result.stdout.rstrip("\n")


def resolve_password(email=None):
    """Resolve password from password file, macOS Keychain, env var, or prompt.

    Order: TIMETREE_PASSWORD_FILE, TIMETREE_KEYCHAIN_SERVICE, TIMETREE_PASSWORD, prompt.
    """
    password_file = os.environ.get("TIMETREE_PASSWORD_FILE")
    if password_file:
        return _read_password_file(password_file)
    keychain_service = os.environ.get("TIMETREE_KEYCHAIN_SERVICE")
    if keychain_service:
        return _read_keychain_password(keychain_service, email)
    env_password = os.environ.get("TIMETREE_PASSWORD")
    if env_password:
        return env_password
    return safe_getpass(prompt="Enter your password: ", echo_char="*")


def configure_logging(verbose):
    """Configure package logging level based on CLI flags."""
    if verbose:
        package_logger.setLevel(logging.DEBUG)


def raw_output_dir(args):
    """Return the raw response output directory for parsed CLI args."""
    return resolve_raw_output_dir(args.developer_mode, args.raw_output_dir)


def list_labels_and_exit(calendar):
    """Print labels for a calendar and return."""
    labels = calendar.get_labels()
    if not labels:
        print("No labels found (the API response format may differ — use -v to debug)")
        return

    for i, (_label_id, label_info) in enumerate(labels.items(), 1):
        color_hex = (label_info.get("color") or "").strip()
        normalized = color_hex.lstrip("#")

        if len(normalized) == 6 and re.fullmatch(r"[0-9A-Fa-f]{6}", normalized):
            r = int(normalized[0:2], 16)
            g = int(normalized[2:4], 16)
            b = int(normalized[4:6], 16)
            dot = f"\033[38;2;{r};{g};{b}m●\033[0m"
        else:
            dot = "●"

        print(f"{i:>2}. {dot} {label_info['name']}")
