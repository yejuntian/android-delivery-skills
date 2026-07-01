#!/usr/bin/env python3
"""Export a Figma frame into a local offline snapshot for Android UI delivery."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIGMA_API_BASE = "https://api.figma.com/v1"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class FigmaTarget:
    file_key: str
    node_id: str
    source_url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Figma node JSON and screenshot into ui/offline_design."
    )
    parser.add_argument("figma_url", help="Figma frame URL with file key and node-id")
    parser.add_argument(
        "--output-dir",
        default="ui/offline_design",
        help="Directory for figma_spec.json, screenshot, and HTML preview",
    )
    parser.add_argument(
        "--token-env",
        default="FIGMA_TOKEN",
        help="Environment variable that stores the Figma personal access token",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=2,
        help="Rendered screenshot scale for the Figma images endpoint",
    )
    parser.add_argument(
        "--image-format",
        choices=("png", "jpg", "svg", "pdf"),
        default="png",
        help="Output image format requested from the Figma images endpoint",
    )
    parser.add_argument(
        "--include-file",
        action="store_true",
        help="Also download file-level metadata in addition to the selected node JSON",
    )
    return parser.parse_args()


def parse_figma_target(figma_url: str) -> FigmaTarget:
    parsed = urllib.parse.urlparse(figma_url)
    if "figma.com" not in parsed.netloc:
        raise ValueError("Not a Figma URL")

    file_match = re.search(r"/(?:design|file|proto)/([A-Za-z0-9]+)", parsed.path)
    if not file_match:
        raise ValueError("Could not extract file key from URL")

    query = urllib.parse.parse_qs(parsed.query)
    raw_node_id = query.get("node-id", [None])[0]
    if not raw_node_id:
        fragment_query = urllib.parse.parse_qs(parsed.fragment)
        raw_node_id = fragment_query.get("node-id", [None])[0]
    if not raw_node_id:
        raise ValueError("Could not extract node-id from URL")

    node_id = raw_node_id.replace("-", ":")
    return FigmaTarget(file_key=file_match.group(1), node_id=node_id, source_url=figma_url)


def figma_get_json(path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = ""
    if params:
        query = "?" + urllib.parse.urlencode(params, doseq=True)
    request = urllib.request.Request(
        FIGMA_API_BASE + path + query,
        headers={"X-Figma-Token": token},
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Figma API {exc.code} for {path}: {body}") from exc


def download_binary(url: str, dest: Path) -> None:
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Asset download failed {exc.code}: {body}") from exc

    dest.write_bytes(data)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def png_header_ok(path: Path) -> bool:
    if not path.exists() or path.suffix.lower() != ".png":
        return False
    with path.open("rb") as handle:
        return handle.read(8) == PNG_SIGNATURE


def render_html_preview(spec_path: Path, image_name: str | None) -> str:
    screenshot = f'<img src="{image_name}" alt="Figma screenshot" />' if image_name else "<p>No screenshot exported.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Figma Offline Snapshot</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; }}
    img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 12px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f7f7f7; padding: 16px; border-radius: 12px; }}
  </style>
</head>
<body>
  <h1>Figma Offline Snapshot</h1>
  <p>Spec file: {spec_path.name}</p>
  {screenshot}
  <h2>Quick use</h2>
  <pre>Read {spec_path.name} first, then compare against the screenshot before generating Android XML.</pre>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        print(
            f"Missing {args.token_env}. Export a token first, for example: export {args.token_env}=...",
            file=sys.stderr,
        )
        return 2

    try:
        target = parse_figma_target(args.figma_url)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    node_payload = figma_get_json(
        f"/files/{target.file_key}/nodes",
        token,
        params={"ids": target.node_id, "geometry": "paths"},
    )

    file_payload: dict[str, Any] | None = None
    if args.include_file:
        file_payload = figma_get_json(f"/files/{target.file_key}", token)

    image_payload = figma_get_json(
        f"/images/{target.file_key}",
        token,
        params={
            "ids": target.node_id,
            "format": args.image_format,
            "scale": args.scale,
        },
    )
    image_url = image_payload.get("images", {}).get(target.node_id)

    image_name: str | None = None
    if image_url:
        image_name = f"frame.{args.image_format}"
        download_binary(image_url, output_dir / image_name)

    spec_payload = {
        "source": {
            "figma_url": target.source_url,
            "file_key": target.file_key,
            "node_id": target.node_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "image_format": args.image_format,
            "scale": args.scale,
        },
        "node_payload": node_payload,
        "image_payload": image_payload,
    }
    if file_payload is not None:
        spec_payload["file_payload"] = file_payload

    spec_path = output_dir / "figma_spec.json"
    write_json(spec_path, spec_payload)
    (output_dir / "index.html").write_text(
        render_html_preview(spec_path, image_name),
        encoding="utf-8",
    )

    if image_name and args.image_format == "png" and not png_header_ok(output_dir / image_name):
        print(
            f"Warning: {image_name} does not have a PNG signature. The export may contain SVG or HTML bytes.",
            file=sys.stderr,
        )

    print(f"Exported spec: {spec_path}")
    if image_name:
        print(f"Exported screenshot: {output_dir / image_name}")
    print(f"Preview page: {output_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
