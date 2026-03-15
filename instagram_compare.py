from __future__ import annotations

import json
from pathlib import Path


class InstagramExportError(ValueError):
    # Custom error type so the bot can show a friendly parsing message.
    """Raised when a file is not a supported Instagram export."""


def _normalize_username(username: str) -> str:
    # Normalize usernames so comparisons are consistent even if formatting differs.
    return username.strip().lstrip("@").lower()


def _extract_followers(data: object) -> set[str]:
    # followers_1.json is a top-level list in Instagram exports.
    if not isinstance(data, list):
        raise InstagramExportError("Followers export must be a JSON list.")

    # Use a set because we only care whether a username exists, not how many times.
    usernames: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue

        # Each follower entry keeps the username in string_list_data[].value.
        for entry in item.get("string_list_data", []):
            if not isinstance(entry, dict):
                continue
            value = entry.get("value")
            if isinstance(value, str) and value.strip():
                usernames.add(_normalize_username(value))

    # If nothing was found, the file probably is not the right export.
    if not usernames:
        raise InstagramExportError("No usernames found in followers export.")

    return usernames


def _extract_following(data: object) -> set[str]:
    # following.json is a top-level object with a relationships_following list.
    if not isinstance(data, dict):
        raise InstagramExportError("Following export must be a JSON object.")

    entries = data.get("relationships_following")
    if not isinstance(entries, list):
        raise InstagramExportError(
            "Following export is missing the relationships_following list."
        )

    # Again, a set keeps the comparison fast and removes duplicates automatically.
    usernames: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue

        # Most following entries store the username directly in the title field.
        title = item.get("title")
        if isinstance(title, str) and title.strip():
            usernames.add(_normalize_username(title))
            continue

        # Fallback in case Instagram changes the structure and puts values in string_list_data.
        for entry in item.get("string_list_data", []):
            if not isinstance(entry, dict):
                continue
            value = entry.get("value")
            if isinstance(value, str) and value.strip():
                usernames.add(_normalize_username(value))

    # An empty result usually means the wrong file was uploaded.
    if not usernames:
        raise InstagramExportError("No usernames found in following export.")

    return usernames


def load_instagram_export(path: str | Path) -> tuple[str, set[str]]:
    # Read the uploaded JSON file from disk.
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    # Detect which export the user uploaded based on its JSON shape.
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
    # These set operations are the core of the whole app.
    followers_only = sorted(followers - following)
    following_only = sorted(following - followers)
    mutual = sorted(followers & following)

    # Return both the counts and the actual username lists for the bot message.
    return {
        "followers_count": len(followers),
        "following_count": len(following),
        "mutual_count": len(mutual),
        "followers_only_count": len(followers_only),
        "following_only_count": len(following_only),
        "followers_only": followers_only,
        "following_only": following_only,
    }
