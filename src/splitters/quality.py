from src.models import Chunk


def check_quality(chunks: list[Chunk], min_chars: int = 50,
                  max_chars: int = 2000) -> list[tuple[Chunk, str]]:
    issues = []
    for chunk in chunks:
        if chunk.char_count < min_chars:
            issues.append((chunk, "too_short"))
        elif chunk.char_count > max_chars:
            issues.append((chunk, "too_long"))
    return issues
