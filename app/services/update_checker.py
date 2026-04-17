from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_OWNER = "gabriellorentzson"
DEFAULT_REPO = "sparam-analysis-tool"


@dataclass(slots=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    html_url: str

    @property
    def is_update_available(self) -> bool:
        return _normalize_version(self.latest_version) > _normalize_version(self.current_version)


def _normalize_version(version: str) -> tuple[int, ...]:
    cleaned = version.strip().lstrip("v")
    parts = []
    for chunk in cleaned.split("."):
        digits = "".join(character for character in chunk if character.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


class UpdateCheckError(RuntimeError):
    """Raised when the latest release cannot be queried."""


class GitHubReleaseChecker:
    def __init__(self, current_version: str, owner: str | None = None, repo: str | None = None) -> None:
        self.current_version = current_version
        self.owner = owner or os.getenv("SPARAM_TOOL_GITHUB_OWNER", DEFAULT_OWNER)
        self.repo = repo or os.getenv("SPARAM_TOOL_GITHUB_REPO", DEFAULT_REPO)

    @property
    def latest_release_url(self) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest"

    def check_for_updates(self, timeout_seconds: float = 3.0) -> UpdateInfo:
        request = Request(
            self.latest_release_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "sparam-analysis-tool",
            },
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise UpdateCheckError(f"Could not query the latest release: {exc}") from exc

        latest_tag = payload.get("tag_name", "")
        html_url = payload.get("html_url", "")
        return UpdateInfo(
            current_version=self.current_version,
            latest_version=latest_tag,
            html_url=html_url,
        )
