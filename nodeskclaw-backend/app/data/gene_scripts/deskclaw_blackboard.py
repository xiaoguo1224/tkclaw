#!/usr/bin/env python3
"""DeskClaw Blackboard Tool -- manage blackboard content, tasks, objectives, and BBS posts.

Usage:
  python3 deskclaw_blackboard.py <action> [options]

Actions:
  get_blackboard                                   Read the full blackboard
  update_blackboard --content TEXT                  Update blackboard markdown content
  patch_section --section HEADING --content TEXT    Update a specific section by heading

  list_tasks [--status STATUS]                     List tasks (pending/in_progress/done/blocked)
  create_task --title TITLE [options]               Create a new task
  update_task --task-id ID [options]                Update a task

  list_objectives                                  List OKR objectives
  create_objective --title TITLE [options]          Create an objective
  update_objective --id ID [options]               Update an objective

  list_posts [--page N]                             List BBS posts
  create_post --title TITLE --content TEXT          Create a BBS post
  get_post --post-id ID                             Get post details with replies
  reply_post --post-id ID --content TEXT            Reply to a post
  update_post --post-id ID [--title T] [--content C]  Edit a post
  delete_post --post-id ID                          Delete a post
  pin_post --post-id ID                             Pin a post
  unpin_post --post-id ID                           Unpin a post

Environment:
  DESKCLAW_API_URL        Backend API base URL
  DESKCLAW_TOKEN          Instance proxy_token
  DESKCLAW_WORKSPACE_ID   Workspace ID
"""

from __future__ import annotations

import argparse
import sys

from _api_client import api_call, _output


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deskclaw_blackboard", description="DeskClaw Blackboard Tool")
    sub = p.add_subparsers(dest="action", required=True)

    sub.add_parser("get_blackboard", help="Read the full blackboard")

    sp = sub.add_parser("update_blackboard", help="Update blackboard markdown content")
    sp.add_argument("--content", required=True)

    sp = sub.add_parser("patch_section", help="Update a section by heading")
    sp.add_argument("--section", required=True, help="Section heading (e.g. '## Notes')")
    sp.add_argument("--content", required=True)

    sp = sub.add_parser("list_tasks", help="List tasks")
    sp.add_argument("--status", choices=["pending", "in_progress", "done", "blocked"])

    sp = sub.add_parser("create_task", help="Create a task")
    sp.add_argument("--title", required=True)
    sp.add_argument("--description")
    sp.add_argument("--priority", default="medium", choices=["urgent", "high", "medium", "low"])
    sp.add_argument("--assignee-id")
    sp.add_argument("--estimated-value", type=float)

    sp = sub.add_parser("update_task", help="Update a task")
    sp.add_argument("--task-id", required=True)
    sp.add_argument("--title")
    sp.add_argument("--description")
    sp.add_argument("--status", choices=["pending", "in_progress", "done", "blocked"])
    sp.add_argument("--priority", choices=["urgent", "high", "medium", "low"])
    sp.add_argument("--assignee-id")
    sp.add_argument("--estimated-value", type=float)
    sp.add_argument("--actual-value", type=float)
    sp.add_argument("--token-cost", type=int)
    sp.add_argument("--blocker-reason")

    sub.add_parser("list_objectives", help="List OKR objectives")

    sp = sub.add_parser("create_objective", help="Create an objective")
    sp.add_argument("--title", required=True)
    sp.add_argument("--description")
    sp.add_argument("--obj-type", default="objective")
    sp.add_argument("--parent-id")

    sp = sub.add_parser("update_objective", help="Update an objective")
    sp.add_argument("--id", required=True)
    sp.add_argument("--title")
    sp.add_argument("--description")
    sp.add_argument("--progress", type=float)
    sp.add_argument("--obj-type")
    sp.add_argument("--parent-id")

    sp = sub.add_parser("list_posts", help="List BBS posts")
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--size", type=int, default=20)

    sp = sub.add_parser("create_post", help="Create a BBS post")
    sp.add_argument("--title", required=True)
    sp.add_argument("--content", required=True)

    sp = sub.add_parser("get_post", help="Get post details")
    sp.add_argument("--post-id", required=True)

    sp = sub.add_parser("reply_post", help="Reply to a post")
    sp.add_argument("--post-id", required=True)
    sp.add_argument("--content", required=True)

    sp = sub.add_parser("update_post", help="Edit a post")
    sp.add_argument("--post-id", required=True)
    sp.add_argument("--title")
    sp.add_argument("--content")

    sp = sub.add_parser("delete_post", help="Delete a post")
    sp.add_argument("--post-id", required=True)

    sp = sub.add_parser("pin_post", help="Pin a post")
    sp.add_argument("--post-id", required=True)

    sp = sub.add_parser("unpin_post", help="Unpin a post")
    sp.add_argument("--post-id", required=True)

    return p


def _optional_fields(args: argparse.Namespace, fields: list[tuple[str, str]]) -> dict:
    """Build a dict from argparse namespace, including only non-None values."""
    body: dict = {}
    for attr, key in fields:
        val = getattr(args, attr, None)
        if val is not None:
            body[key] = val
    return body


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    action = args.action
    bb = "/blackboard"

    if action == "get_blackboard":
        _output(api_call("GET", bb))

    elif action == "update_blackboard":
        _output(api_call("PUT", bb, {"content": args.content}))

    elif action == "patch_section":
        _output(api_call("PATCH", f"{bb}/sections", {"section": args.section, "content": args.content}))

    elif action == "list_tasks":
        params = []
        if args.status:
            params.append(f"status={args.status}")
        qs = f"?{'&'.join(params)}" if params else ""
        _output(api_call("GET", f"{bb}/tasks{qs}"))

    elif action == "create_task":
        body = {"title": args.title, "priority": args.priority}
        if args.description:
            body["description"] = args.description
        if args.assignee_id:
            body["assignee_id"] = args.assignee_id
        if args.estimated_value is not None:
            body["estimated_value"] = args.estimated_value
        _output(api_call("POST", f"{bb}/tasks", body))

    elif action == "update_task":
        body = _optional_fields(args, [
            ("title", "title"), ("description", "description"), ("status", "status"),
            ("priority", "priority"), ("assignee_id", "assignee_id"),
            ("estimated_value", "estimated_value"), ("actual_value", "actual_value"),
            ("token_cost", "token_cost"), ("blocker_reason", "blocker_reason"),
        ])
        _output(api_call("PUT", f"{bb}/tasks/{args.task_id}", body))

    elif action == "list_objectives":
        _output(api_call("GET", f"{bb}/objectives"))

    elif action == "create_objective":
        body = {"title": args.title, "obj_type": args.obj_type}
        if args.description:
            body["description"] = args.description
        if args.parent_id:
            body["parent_id"] = args.parent_id
        _output(api_call("POST", f"{bb}/objectives", body))

    elif action == "update_objective":
        body = _optional_fields(args, [
            ("title", "title"), ("description", "description"),
            ("progress", "progress"), ("obj_type", "obj_type"), ("parent_id", "parent_id"),
        ])
        _output(api_call("PUT", f"{bb}/objectives/{args.id}", body))

    elif action == "list_posts":
        _output(api_call("GET", f"{bb}/posts?page={args.page}&size={args.size}"))

    elif action == "create_post":
        _output(api_call("POST", f"{bb}/posts", {"title": args.title, "content": args.content}))

    elif action == "get_post":
        _output(api_call("GET", f"{bb}/posts/{args.post_id}"))

    elif action == "reply_post":
        _output(api_call("POST", f"{bb}/posts/{args.post_id}/replies", {"content": args.content}))

    elif action == "update_post":
        body = _optional_fields(args, [("title", "title"), ("content", "content")])
        _output(api_call("PUT", f"{bb}/posts/{args.post_id}", body))

    elif action == "delete_post":
        _output(api_call("DELETE", f"{bb}/posts/{args.post_id}"))

    elif action == "pin_post":
        _output(api_call("POST", f"{bb}/posts/{args.post_id}/pin"))

    elif action == "unpin_post":
        _output(api_call("DELETE", f"{bb}/posts/{args.post_id}/pin"))


if __name__ == "__main__":
    main()
