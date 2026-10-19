"""Generate one short Omni video; --dry-run never loads credentials or calls Google."""

import argparse
import base64
import binascii
import json
import os
from pathlib import Path

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from requests.exceptions import RequestException


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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--model", default="gemini-omni-1.1-flash-preview")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--credentials", type=Path, default=Path(__file__).with_name("service_account.json"))
    parser.add_argument("--output", type=Path, default=Path("omni-test.mp4"))
    parser.add_argument("--dry-run", action="store_true", help="Show request only; no credentials or network access.")
    args = parser.parse_args(argv)

    if args.prompt is None:
        prompt_file = Path(__file__).parent / "prompt.txt"
        if prompt_file.exists():
            args.prompt = prompt_file.read_text(encoding="utf-8").strip()
        else:
            parser.exit(1, f"No prompt provided. Create a 'prompt.txt' file in {Path(__file__).parent} or use --prompt argument.\n")

    input_data = [{"type": "text", "text": args.prompt}]
    
    payload = {
        "model": args.model,
        "input": input_data,
        "response_format": [{
            "type": "video", "duration": "5s", "resolution": "720p", "aspect_ratio": "16:9",
        }],
        "generation_config": {"video_config": {"task": "text_to_video"}},
    }
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0

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
                    "Could not load credentials, decode a completed video, or save output. Check configuration and output path.\n")
    print(f"Saved {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
