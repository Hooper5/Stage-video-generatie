"""Generate one short Omni video; --dry-run never loads credentials or calls Google."""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime
import json
import os
import re
from pathlib import Path

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from requests.exceptions import RequestException

import requests
from urllib.parse import urlparse


BASE_DIR = Path(__file__).parent
PROMPT_FILE = BASE_DIR / "prompt.txt"
IMAGES_DIR = BASE_DIR / "images"
START_END_SLOTS = [
    ("start", "Start frame (the video must begin with this image as its first frame):"),
    ("end", "End frame (the video must end with this image as its final frame; do not use it as the thumbnail):"),
]
REFERENCE_LABEL = "Reference image{number} (use for subject/style/appearance):"


def find_reference_images() -> list[Path]:
    """Return reference.jpg, reference1.jpg, reference2.jpg, ... sorted by number."""
    matches = [(p, re.fullmatch(r"reference(\d*)", p.stem)) for p in IMAGES_DIR.glob("reference*.jpg")]
    return [p for p, m in sorted(((p, m) for p, m in matches if m), key=lambda pm: int(pm[1].group(1) or 0))]


def video_bytes(interaction: dict) -> bytes:
    if interaction.get("status") != "completed":
        raise ValueError("Generation did not complete; no video saved.")
    for step in interaction.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for content in step.get("content", []):
            if content.get("type") == "video" and content.get("data"):
                data = base64.b64decode(content["data"], validate=True)
                if data:
                    return data
    raise ValueError("No inline video returned. Check model access and safety filtering.")


def read_and_encode_image(image_source: str | Path) -> tuple[str, str]:
    """Load a local image or download an HTTP(S) image and return base64 data plus MIME type."""
    source = str(image_source)
    parsed_url = urlparse(source)

    if parsed_url.scheme in ("http", "https"):
        response = requests.get(source, timeout=(10, 30))
        response.raise_for_status()

        image_data = response.content
        mime_type = response.headers.get("Content-Type", "image/jpeg").split(";", 1)[0]

        if not mime_type.startswith("image/"):
            raise ValueError(
                f"URL did not return an image. Received Content-Type: {mime_type}"
            )
    else:
        image_path = Path(source)

        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        image_data = image_path.read_bytes()

        suffix_to_mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        mime_type = suffix_to_mime.get(image_path.suffix.lower(), "image/jpeg")

    if not image_data:
        raise ValueError(f"Image contains no data: {source}")

    return base64.b64encode(image_data).decode("utf-8"), mime_type

def main(argv=None) -> int:
    print(datetime.datetime.now())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemini-omni-1.1-flash-preview")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--credentials", type=Path, default=Path(__file__).with_name("service_account.json"))
    parser.add_argument("--output", type=Path, default=Path("one step recipe to video with end reference.mp4"))
    parser.add_argument("--dry-run", action="store_true", help="Show request only; no credentials or network access.")
    args = parser.parse_args(argv)

    try:
        prompt_text = PROMPT_FILE.read_text(encoding="utf-8").strip()
    except OSError as e:
        parser.exit(1, f"Could not read prompt file {PROMPT_FILE}: {e}\n")
    if not prompt_text:
        parser.exit(1, f"Prompt file is empty: {PROMPT_FILE}\n")

    input_items = [{"type": "text", "text": prompt_text}]

    payload = {
        "model": args.model,
        "input": input_items,
        "response_format": [{
            "type": "video", "duration": "5s", "resolution": "720p", "aspect_ratio": "16:9",
        }],
        "generation_config": {"video_config": {"task": "reference_to_video"}},
    }

    images_to_send = []
    for index, image_path in enumerate(find_reference_images(), start=1):
        label = REFERENCE_LABEL.format(number=f" {index}")
        images_to_send.append((image_path, label))
    for name, label in START_END_SLOTS:
        image_path = IMAGES_DIR / f"{name}.jpg"
        if image_path.is_file():
            images_to_send.append((image_path, label))

    for image_path, label in images_to_send:
        try:
            image_data, mime_type = read_and_encode_image(image_path)
        except (OSError, ValueError) as e:
            parser.exit(1, f"Could not load {image_path.name}: {e}\n")
        input_items.append({"type": "text", "text": label})
        input_items.append({"type": "image", "data": image_data, "mime_type": mime_type})
        print(f"Using {image_path.name}: {label}")

    if args.output.exists():
        parser.exit(1, "Output already exists; choose another --output path.\n")
    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(args.credentials), scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        project = args.project or credentials.project_id
        if not project:
            parser.exit(1, "Set --project or GOOGLE_CLOUD_PROJECT.\n")
        url = f"https://aiplatform.googleapis.com/v1beta1/projects/{project}/locations/global/interactions"
        print("Requesting one 3-second Omni video (billable); this can take several minutes.")
        with AuthorizedSession(credentials, max_refresh_attempts=0) as session:
            response = session.post(url, json=payload, timeout=(30, 600))
            if not response.ok:
                # Avoid printing response odies, request headers, or credentials.
                print(response.text)
                parser.exit(1,
                            f"Google API returned HTTP {response.status_code}. Check billing, API enablement, model access, and IAM.\n")
            data = video_bytes(response.json())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as output:
            output.write(data)
    except RequestException:
        parser.exit(1, "Network request failed or timed out. Generation may still be billed; do not blindly retry.\n")
    except GoogleAuthError:
        parser.exit(1, "Authentication failed. Check the service account and its permissions.\n")
    except (OSError, ValueError, binascii.Error):
        parser.exit(1,
                    "Could not load credentials, decode a completed video, save output, or process image. Check configuration, output path, and last-frame file.\n")
    print(f"Saved {args.output}")
    print(datetime.datetime.now())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
