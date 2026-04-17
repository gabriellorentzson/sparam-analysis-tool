# Desktop S-Parameter Analysis Tool

Windows desktop application for loading and analyzing Touchstone `.s4p` files with a focus on differential channel work. The MVP provides mixed-mode S-parameter analysis, insertion loss plotting, differential TDR, summary metrics, GitHub-based release packaging, and a basic update checker.

## Features

- Load one or more `.s4p` files
- Show enabled/disabled files in a checklist panel
- Compute mixed-mode `SDD11` and `SDD21` from 4-port single-ended data
- Plot `SDD21` in dB versus frequency
- Plot differential TDR impedance versus time
- Show summary metrics per file, including `SDD21` at 13.28 GHz and 26.5625 GHz
- Add a basic marker on each plot by clicking inside the axes
- Check GitHub Releases for updates on startup or manually
- Package the app with PyInstaller

## Project Layout

```text
app/
  analysis/
  models/
  plots/
  services/
  ui/
tests/
.github/workflows/
```

## Local Development

1. Create and activate a virtual environment.
2. Install dependencies:

```powershell
python -m pip install -e .[dev]
```

3. Run the desktop app:

```powershell
python -m app.main
```

## Running Tests

```powershell
pytest
```

## Packaging

Build a Windows executable with PyInstaller:

```powershell
pyinstaller sparam_tool.spec --noconfirm
```

The packaged executable will be placed under `dist/`.

## GitHub Releases and Updates

The app includes a lightweight GitHub Release update checker. Configure the repository owner and name with environment variables if you want to reuse the code in another repository:

```powershell
$env:SPARAM_TOOL_GITHUB_OWNER = "your-org-or-user"
$env:SPARAM_TOOL_GITHUB_REPO = "your-repo"
```

When those variables are not set, the app falls back to placeholder values in [`app/services/update_checker.py`](/D:/codex/sparam_proj/app/services/update_checker.py).

## Release Workflow

The GitHub Actions workflow:

- installs dependencies
- runs tests
- builds the PyInstaller artifact
- uploads the build artifact for all pushes
- publishes the packaged app on GitHub Releases for version tags like `v0.1.0`

## Notes on TDR

- Apparent TDR resolution is bandwidth-limited by the highest measured frequency in the source file.
- Higher point density improves display smoothness but does not create new measured resolution.
- The implementation supports optional windowing in the analysis layer so the UI can expose more controls later.
