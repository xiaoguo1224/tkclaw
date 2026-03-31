"""CLI entry point for standalone tunnel bridge."""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="NoDeskClaw tunnel bridge")
    parser.add_argument(
        "--runtime",
        required=True,
        help="Target runtime to bridge",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    print(f"Unsupported runtime: {args.runtime}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
