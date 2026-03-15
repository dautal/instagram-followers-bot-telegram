from __future__ import annotations

import json
from pathlib import Path


class InstagramExportError(ValueError):
    """Raised when a file is not a supported Instagram export."""


def _normalize_username(username: str) -> str:
    return username.strip().lstrip("@").lower()


def _extract_followers(data: object) -> set[str]:
    if not isinstance(data, list):
        raise InstagramExportError("Followers export must be a JSON list.")

    usernames: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue

        # In followers_1.json, the username lives in string_list_data[].value.
        for entry in item.get("string_list_data", []):
            if not isinstance(entry, dict):
                continue
            value = entry.get("value")
            if isinstance(value, str) and value.strip():
                usernames.add(_normalize_username(value))

    if not usernames:
        raise InstagramExportError("No usernames found in followers export.")

    return usernames


def _extract_following(data: object) -> set[str]:
    if not isinstance(data, dict):
        raise InstagramExportError("Following export must be a JSON object.")

    entries = data.get("relationships_following")
    if not isinstance(entries, list):
        raise InstagramExportError(
            "Following export is missing the relationships_following list."
        )

    usernames: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue

        # In following.json, Instagram stores the username in the title field.
        title = item.get("title")
        if isinstance(title, str) and title.strip():
            usernames.add(_normalize_username(title))
            continue

        for entry in item.get("string_list_data", []):
            if not isinstance(entry, dict):
                continue
            value = entry.get("value")
            if isinstance(value, str) and value.strip():
                usernames.add(_normalize_username(value))

    if not usernames:
        raise InstagramExportError("No usernames found in following export.")

    return usernames


def load_instagram_export(path: str | Path) -> tuple[str, set[str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    # Instagram uses different top-level shapes for followers vs following exports.
    if isinstance(data, list):
        return "followers", _extract_followers(data)

    if isinstance(data, dict) and "relationships_following" in data:
        return "following", _extract_following(data)

    raise InstagramExportError(
        "Unsupported file format. Upload followers_1.json or following.json from Instagram."
    )


def compare_usernames(
    followers: set[str], following: set[str]
) -> dict[str, list[str] | int]:
    # Set differences give the one-sided relationships directly.
    followers_only = sorted(followers - following)
    following_only = sorted(following - followers)
    mutual = sorted(followers & following)

    return {
        "followers_count": len(followers),
        "following_count": len(following),
        "mutual_count": len(mutual),
        "followers_only_count": len(followers_only),
        "following_only_count": len(following_only),
        "followers_only": followers_only,
        "following_only": following_only,
    }
