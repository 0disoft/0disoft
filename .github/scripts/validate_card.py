"""Validate a newly generated detailed Buildmarks card using the standard library."""

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

SVG = "{http://www.w3.org/2000/svg}"


def validate_card(path, scope, generated_since, today=None):
    today = today or datetime.now(timezone.utc).date()
    started = date.fromisoformat(generated_since)
    if not today - timedelta(days=1) <= started <= today:
        raise ValueError("Generation must have started today or across UTC midnight")

    content = Path(path).read_bytes()
    if len(content) < 3000:
        raise ValueError("Card is missing or truncated (expected at least 3000 bytes)")
    root = ET.fromstring(content)
    if root.tag != f"{SVG}svg":
        raise ValueError("Expected an SVG root in the SVG namespace")
    if (root.get("width"), root.get("height")) != ("760", "420"):
        raise ValueError("Expected the 760x420 detailed layout")

    texts = list(root.iter(f"{SVG}text"))
    metrics = [node for node in texts if "metric" in node.get("class", "").split()]
    if len(metrics) != 6:
        raise ValueError(f"Expected 6 metric rows, found {len(metrics)}")
    footers = [node for node in texts if "footer" in node.get("class", "").split()]
    if len(footers) != 1:
        raise ValueError("Expected exactly one card footer")
    footer = "".join(footers[0].itertext()).strip()
    match = re.fullmatch(r"Buildmarks v\S+ · " + re.escape(scope) + r" · (\d{4}-\d{2}-\d{2})", footer)
    if not match:
        raise ValueError("Footer has the wrong data scope or no generation date")
    generated = date.fromisoformat(match[1])
    if not started <= generated <= today:
        raise ValueError(f"Card date {generated} falls outside this generation ({started}..{today})")
    return f"Card validated: {len(content)} bytes, 6 score rows, scope {scope}, date {generated}."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card", type=Path)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--generated-since", required=True)
    args = parser.parse_args()
    try:
        print(validate_card(args.card, args.scope, args.generated_since))
    except (OSError, ValueError, ET.ParseError) as error:
        # Keep parser errors out of workflow-command syntax and on one line.
        message = str(error).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Invalid Buildmarks card::{message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
