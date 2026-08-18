import base64
import json
from google import genai
from google.genai import types


def solveCaptcha(base64_image: str, api_key: str) -> dict:

    base64_image = base64_image.strip().replace("\n", "").replace("\r", "")
    if "base64," in base64_image:
        base64_image = base64_image.split("base64,")[1]


    image_bytes = base64.b64decode(base64_image)

    client = genai.Client(api_key=api_key)

    system_instruction = (
        "You are an OCR system. Identify all letters in the provided image. "
        "Respect upper and lowercase letters, and omit any spaces."
    )

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema={
            "type": "OBJECT",
            "properties": {
                "status":  {"type": "STRING"},
                "letters": {"type": "STRING"},
            },
            "required": ["status", "letters"],
        },
    )

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite", #Highest free limit
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            "Read the letters in this image.",
        ],
        config=config,
    )


    return json.loads(response.text)