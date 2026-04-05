import json
import re


def extract_inline_metadata(content: str) -> tuple[dict, str]:
    pattern = r'^(?:#|<!--)\s*METADATA=({.*?})\s*(?:-->)?\s*\n'
    match = re.match(pattern, content)
    if match:
        return json.loads(match.group(1)), content[match.end():]
    return {}, content
