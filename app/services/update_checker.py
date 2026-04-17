from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_OWNER = "gabriellorentzson"
DEFAULT_REPO = "sparam-analysis-tool"


@dataclass(slots=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    html_url: str
    asset_name: str = ""
    asset_download_url: str = ""

    @property
    def is_update_available(self) -> bool:
        return _normalize_version(self.latest_version) > _normalize_version(self.current_version)


@dataclass(slots=True)
class PreparedUpdate:
    script_path: str
    source_dir: str
    target_dir: str
    executable_path: str
    parent_pid: int
    log_path: str


def _normalize_version(version: str) -> tuple[int, ...]:
    cleaned = version.strip().lstrip("v")
    parts = []
    for chunk in cleaned.split("."):
        digits = "".join(character for character in chunk if character.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


class UpdateCheckError(RuntimeError):
    """Raised when the latest release cannot be queried."""


class UpdateInstallError(RuntimeError):
    """Raised when an automatic update cannot be prepared."""


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
        asset_name = ""
        asset_download_url = ""
        for asset in payload.get("assets", []):
            candidate_name = str(asset.get("name", ""))
            if candidate_name.lower().endswith(".zip"):
                asset_name = candidate_name
                asset_download_url = str(asset.get("browser_download_url", ""))
                break
        return UpdateInfo(
            current_version=self.current_version,
            latest_version=latest_tag,
            html_url=html_url,
            asset_name=asset_name,
            asset_download_url=asset_download_url,
        )


def can_self_update() -> bool:
    return bool(getattr(sys, "frozen", False))


def _resolve_extracted_payload_root(extracted_dir: Path) -> Path:
    expected_folder = extracted_dir / "SParamAnalysisTool"
    if expected_folder.is_dir():
        return expected_folder
    return extracted_dir


def prepare_windows_self_update(update_info: UpdateInfo, timeout_seconds: float = 60.0) -> PreparedUpdate:
    if not can_self_update():
        raise UpdateInstallError("Automatic install is only available from the packaged app.")
    if not update_info.asset_download_url:
        raise UpdateInstallError("No downloadable release asset was found for this version.")

    install_dir = Path(sys.executable).resolve().parent
    executable_path = str(Path(sys.executable).resolve())
    staging_root = Path(tempfile.mkdtemp(prefix="sparam_tool_update_"))
    archive_path = staging_root / (update_info.asset_name or "update.zip")
    extracted_dir = staging_root / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    log_path = staging_root / "update.log"

    request = Request(
        update_info.asset_download_url,
        headers={"User-Agent": "sparam-analysis-tool"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response, archive_path.open("wb") as destination:
            destination.write(response.read())
    except (HTTPError, URLError, TimeoutError) as exc:
        raise UpdateInstallError(f"Could not download the update asset: {exc}") from exc

    try:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extracted_dir)
    except zipfile.BadZipFile as exc:
        raise UpdateInstallError("Downloaded update asset is not a valid zip file.") from exc
    payload_root = _resolve_extracted_payload_root(extracted_dir)

    script_path = staging_root / "apply_update.ps1"
    script_contents = textwrap.dedent(
        """
        param(
            [string]$SourceDir,
            [string]$TargetDir,
            [string]$ExecutablePath,
            [int]$ParentPid,
            [string]$LogPath
        )

        function Write-Log {
            param([string]$Message)
            Add-Content -LiteralPath $LogPath -Value ("[{0}] {1}" -f (Get-Date -Format s), $Message)
        }

        Write-Log "Updater started"
        Write-Log "SourceDir=$SourceDir"
        Write-Log "TargetDir=$TargetDir"
        Write-Log "ExecutablePath=$ExecutablePath"
        Write-Log "ParentPid=$ParentPid"

        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            $proc = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
            if ($null -eq $proc) {
                Write-Log "Parent process exited"
                break
            }
            Start-Sleep -Milliseconds 500
        }

        $copied = $false
        for ($attempt = 0; $attempt -lt 15; $attempt++) {
            & robocopy $SourceDir $TargetDir /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
            Write-Log ("Robocopy exit code: {0}" -f $LASTEXITCODE)
            if ($LASTEXITCODE -lt 8) {
                $copied = $true
                break
            }
            Start-Sleep -Seconds 1
        }

        if (-not $copied) {
            Write-Log "Copy failed after retries"
            exit 1
        }

        Start-Sleep -Seconds 1
        if (-not (Test-Path -LiteralPath $ExecutablePath)) {
            Write-Log "Executable not found after copy"
            exit 1
        }

        Write-Log "Launching updated executable"
        Start-Process -FilePath $ExecutablePath -WorkingDirectory $TargetDir
        """
    ).strip()
    script_path.write_text(script_contents, encoding="utf-8")

    creation_flags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creation_flags |= subprocess.DETACHED_PROCESS

    return PreparedUpdate(
        script_path=str(script_path),
        source_dir=str(payload_root),
        target_dir=str(install_dir),
        executable_path=executable_path,
        parent_pid=os.getpid(),
        log_path=str(log_path),
    )


def launch_prepared_update(prepared_update: PreparedUpdate) -> None:
    powershell_exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if not os.path.exists(powershell_exe):
        powershell_exe = "powershell.exe"
    try:
        subprocess.Popen(
            [
                powershell_exe,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                prepared_update.script_path,
                prepared_update.source_dir,
                prepared_update.target_dir,
                prepared_update.executable_path,
                str(prepared_update.parent_pid),
                prepared_update.log_path,
            ],
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateInstallError(f"Could not launch the update helper: {exc}") from exc
