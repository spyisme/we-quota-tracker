import json
import urllib.request
import urllib.error


def solveCaptcha(base64_image: str, api_key: str) -> dict:
    """Solves captcha image using Google Gemini 2.5 Flash with structured JSON output."""
    base64_image = base64_image.strip().replace("\n", "").replace("\r", "")
    if "base64," in base64_image:
        base64_image = base64_image.split("base64,")[1]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

    payload = {
        "system_instruction": {
            "parts": [{
                "text": (
                    "You are an OCR system. Identify all letters in the provided image. "
                    "Respect upper and lowercase letters, and omit any spaces."
                )
            }]
        },
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64_image,
                    }
                },
                {"text": "Read the letters in this image."},
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "OBJECT",
                "properties": {
                    "status": {"type": "STRING"},
                    "letters": {"type": "STRING"},
                },
                "required": ["status", "letters"],
            },
        },
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    # Extract structured JSON returned in first candidate part
    raw_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`").strip()
        if raw_text.startswith("json"):
            raw_text = raw_text[4:].strip()

    return json.loads(raw_text)