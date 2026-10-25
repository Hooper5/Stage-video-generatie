import os
import base64
import argparse
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv()


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROMPT_FILE = SCRIPT_DIR / "prompt.txt"


def read_prompt_from_file(prompt_file: Path) -> str:
    if not prompt_file.exists():
        raise FileNotFoundError(
            f"Geen prompt gevonden. Maak een prompt.txt bestand aan in dezelfde directory: {prompt_file}"
        )

    prompt = prompt_file.read_text(encoding="utf-8").strip()

    if not prompt:
        raise ValueError(f"De prompt file is leeg: {prompt_file}")

    return prompt


def generate_image(prompt: str, output_path: str, model: str, size: str) -> None:
    api_key = os.getenv("GENAI_API_KEY")
    base_url = os.getenv("GENAI_BASE_URL", "https://api-ai.digitaldev.nl").rstrip("/")

    if not api_key:
        raise RuntimeError("Geen GENAI_API_KEY gevonden. Controleer je .env file.")

    if not model:
        raise RuntimeError("Geen model gevonden. Zet GENAI_IMAGE_MODEL in je .env of gebruik --model.")

    url = f"{base_url}/openai/v1/images/generations"

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
    }

    print(f"POST {url}")
    print(f"Model: {model}")
    print(f"Size: {size}")
    print(f"Prompt gelezen ({len(prompt)} tekens)")

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=180,
    )

    if response.status_code != 200:
        print("Request mislukt.")
        print(f"Status code: {response.status_code}")
        print("Response:")
        print(response.text)
        return

    data = response.json()

    if "data" not in data or not data["data"]:
        print("Geen image data gevonden in response.")
        print(data)
        return

    first_image = data["data"][0]

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if "b64_json" in first_image and first_image["b64_json"]:
        image_bytes = base64.b64decode(first_image["b64_json"])
        output.write_bytes(image_bytes)
        print(f"Afbeelding opgeslagen als: {output}")
        return

    if "url" in first_image and first_image["url"]:
        image_url = first_image["url"]
        image_response = requests.get(image_url, timeout=180)
        image_response.raise_for_status()
        output.write_bytes(image_response.content)
        print(f"Afbeelding opgeslagen als: {output}")
        return

    print("Onbekend image response-formaat:")
    print(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genereer een afbeelding via AH Gen AI Platform."
    )

    parser.add_argument(
        "--prompt",
        required=False,
        help="Beschrijving van de afbeelding. Als je dit niet meegeeft, wordt prompt.txt gebruikt.",
    )

    parser.add_argument(
        "--prompt-file",
        default=str(DEFAULT_PROMPT_FILE),
        help="Pad naar promptbestand. Standaard: prompt.txt naast dit script.",
    )

    parser.add_argument(
        "--output",
        default="reference.jpg",
        help="Output-bestand, bijvoorbeeld reference.jpg.",
    )

    parser.add_argument(
        "--model",
        default=os.getenv("GENAI_IMAGE_MODEL", "gpt-image-2"),
        help="Image model. Standaard: gpt-image-2.",
    )

    parser.add_argument(
        "--size",
        default="1024x1024",
        help="Afbeeldingsgrootte, bijvoorbeeld 1024x1024.",
    )

    args = parser.parse_args()

    if args.prompt:
        final_prompt = args.prompt.strip()
    else:
        final_prompt = read_prompt_from_file(Path(args.prompt_file))

    generate_image(
        prompt=final_prompt,
        output_path=args.output,
        model=args.model,
        size=args.size,
    )
