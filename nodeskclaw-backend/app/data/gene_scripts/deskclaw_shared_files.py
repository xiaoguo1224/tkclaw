#!/usr/bin/env python3
"""DeskClaw Shared Files Tool -- manage workspace shared files.

Usage:
  python3 deskclaw_shared_files.py <action> [options]

Actions:
  list_files [--path /]              List files in a directory
  read_file --file-id ID             Read file content (returns base64)
  write_file --filename NAME [--content TEXT | --file-path PATH]
             [--parent-path /] [--content-type TYPE]
                                     Upload a file directly
  delete_file --file-id ID           Delete a file
  mkdir --name NAME [--parent-path /]  Create a directory
  get_file_url --file-id ID          Get download URL for a file

Environment:
  DESKCLAW_API_URL        Backend API base URL
  DESKCLAW_TOKEN          Instance proxy_token
  DESKCLAW_WORKSPACE_ID   Workspace ID
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from _api_client import api_call, api_upload_file, _output


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deskclaw_shared_files", description="DeskClaw Shared Files Tool")
    sub = p.add_subparsers(dest="action", required=True)

    sp = sub.add_parser("list_files", help="List files in a directory")
    sp.add_argument("--path", default="/", help="Parent directory path (default: /)")

    sp = sub.add_parser("read_file", help="Read file content")
    sp.add_argument("--file-id", required=True)

    sp = sub.add_parser("write_file", help="Upload a file")
    sp.add_argument("--filename", required=True)
    group = sp.add_mutually_exclusive_group(required=True)
    group.add_argument("--content", help="Raw UTF-8 text content")
    group.add_argument("--file-path", help="Local file path to upload directly")
    sp.add_argument("--parent-path", default="/")
    sp.add_argument("--content-type", default="application/octet-stream")

    sp = sub.add_parser("delete_file", help="Delete a file")
    sp.add_argument("--file-id", required=True)

    sp = sub.add_parser("mkdir", help="Create a directory")
    sp.add_argument("--name", required=True)
    sp.add_argument("--parent-path", default="/")

    sp = sub.add_parser("get_file_url", help="Get download URL for a file")
    sp.add_argument("--file-id", required=True)

    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    action = args.action
    base = "/blackboard/files"

    if action == "list_files":
        _output(api_call("GET", f"{base}?parent_path={args.path}"))

    elif action == "read_file":
        _output(api_call("GET", f"{base}/{args.file_id}/content"))

    elif action == "write_file":
        if args.file_path:
            file_content = Path(args.file_path).read_bytes()
        else:
            file_content = args.content.encode("utf-8")
        _output(api_upload_file(
            f"{base}/upload",
            fields={"parent_path": args.parent_path},
            filename=args.filename,
            file_content=file_content,
            content_type=args.content_type,
        ))

    elif action == "delete_file":
        _output(api_call("DELETE", f"{base}/{args.file_id}"))

    elif action == "mkdir":
        body = {"name": args.name, "parent_path": args.parent_path}
        _output(api_call("POST", f"{base}/mkdir", body))

    elif action == "get_file_url":
        _output(api_call("GET", f"{base}/{args.file_id}/url"))


if __name__ == "__main__":
    main()
