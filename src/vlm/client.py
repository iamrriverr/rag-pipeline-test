from openai import OpenAI
import base64
from src.config import settings
from src.vlm.prompts import TABLE_PROMPT, IMAGE_PROMPT


class VLMClient:
    def __init__(self):
        self._client = OpenAI(api_key=settings.openai_api_key)

    def table_to_text(self, image_bytes: bytes) -> str:
        return self._call(image_bytes, TABLE_PROMPT)

    def image_to_text(self, image_bytes: bytes) -> str:
        return self._call(image_bytes, IMAGE_PROMPT)

    def _call(self, image_bytes: bytes, system_prompt: str) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        response = self._client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{b64}"
                    }}
                ]}
            ],
            max_tokens=2000,
        )
        return response.choices[0].message.content
