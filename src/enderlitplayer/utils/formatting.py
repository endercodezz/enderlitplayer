"""Human-readable formatting helpers."""

from __future__ import annotations


def format_time(seconds: float) -> str:
    """Format seconds as ``m:ss`` (or ``h:mm:ss`` for long durations)."""
    if not seconds or seconds <= 0:
        return "0:00"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def initials(text: str, limit: int = 2) -> str:
    words = [word for word in (text or "").split() if word[:1].isalnum()]
    if not words:
        return "♪"
    if len(words) == 1:
        return words[0][:limit].upper()
    return "".join(word[0] for word in words[:limit]).upper()
