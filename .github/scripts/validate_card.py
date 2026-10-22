"""Validate a newly generated compact Buildmarks card using the standard library."""

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
    height = "304" if scope == "Public + Private Projects" else "280"
    if root.get("data-layout") != "compact" or (root.get("width"), root.get("height")) != ("420", height):
        raise ValueError(f"Expected the 420x{height} compact layout")

    texts = list(root.iter(f"{SVG}text"))
    scores = [node for node in root.iter() if "profile-score" in node.get("class", "").split()]
    if len(scores) != 1 or not re.fullmatch(r"\d{1,3}", "".join(scores[0].itertext()).strip()):
        raise ValueError("Expected one numeric profile score")
    if not 0 <= int("".join(scores[0].itertext()).strip()) <= 100:
        raise ValueError("Profile score must be between 0 and 100")
    labels = [node.get("aria-label", "") for node in root.iter(f"{SVG}g")]
    scope_label = "Public GitHub projects" if scope == "Public GitHub" else scope
    if not any(label.startswith(scope_label + " · ") for label in labels):
        raise ValueError("Card has the wrong data scope")
    generated_labels = [label for label in labels if label.startswith("Generated ")]
    if len(generated_labels) != 1:
        raise ValueError("Expected one generation date")
    match = re.fullmatch(r"Generated (\d{4}-\d{2}-\d{2}) · v\S+", generated_labels[0])
    if not match:
        raise ValueError("Card has no generation date or version")
    footers = [node for node in texts if "footer" in node.get("class", "").split()]
    if not any("".join(footer.itertext()).strip() == match[1] for footer in footers):
        raise ValueError("Visible footer is missing the generation date")
    generated = date.fromisoformat(match[1])
    if not started <= generated <= today:
        raise ValueError(f"Card date {generated} falls outside this generation ({started}..{today})")
    return f"Card validated: {len(content)} bytes, compact layout, scope {scope}, date {generated}."


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
