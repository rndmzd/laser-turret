# Repository Guidelines

## Project Structure & Module Organization
- Source code for runtime controllers lives in `laserturret/`, split into hardware drivers, configuration helpers, and motion logic (`motion/`).
- `app.py` hosts the Flask + Socket.IO control panel; static assets and templates sit in `static/` and `templates/`.
- Calibration assets (crosshair, configs, recordings) live under `media/`, `models/`, and root `*.json`; scripts for hardware bring-up are in `scripts/`.
- Deployment and reference docs are in `docs/`, while environment examples sit in `laserturret.conf` and `.example`.

## Build, Test, and Development Commands
- `python3 -m venv env && source env/bin/activate` to isolate dependencies; keep the repo's existing `env/` directory out of commits.
- `pip install -r requirements.txt` installs Flask, camera, GPIO, and detection tooling; run again after editing dependencies.
- `python app.py` launches the control panel on port 5000 with WebSocket updates; use `FLASK_ENV=development` locally for verbose logs.
- `pytest` targets future unit coverage; for hardware smoke tests run `python scripts/test_with_mock_hardware.py`.

## Coding Style & Naming Conventions
- Follow PEP 8: 4-space indents, snake_case modules (`lasercontrol.py`), CamelCase classes, and short, descriptive function names.
- Prefer explicit imports from sibling modules instead of wildcard imports; keep hardware pin constants grouped at the top of files.
- When adding configuration options, mirror the existing INI naming (lowercase with underscores) and document them in `laserturret.conf.example`.

## Testing Guidelines
- Automated tests should mock GPIO, Picamera2, and MQTT endpoints; keep real hardware access behind feature flags so `pytest` can run on CI.
- Name tests `test_<module>.py` and co-locate them beside the code or under `tests/` once created; reuse fixtures in `scripts/test_with_mock_hardware.py`.
- For integration checks, capture dry-run output (e.g., `python scripts/steppercontrol_test.py --dry-run`) and attach logs to pull requests.

## Commit & Pull Request Guidelines
- Follow the existing imperative, sentence-case style (e.g., "Moves style elements from HTML head to dedicated CSS file"); keep messages under 72 characters with context in the body.
- Reference issues with `Fixes #ID` when applicable, and squash trivial fixups before submission.
- Pull requests should describe hardware setups, configuration knobs touched, test evidence (commands + results), and include screenshots of UI changes.

## Security & Configuration Tips
- Never commit real secrets; copy `laserturret.conf.example` when creating new variants and document sensitive values with placeholders.
- Rotate the Flask `SECRET_KEY` before deploying; verify GPIO pins and laser power limits in config reviews to prevent unsafe defaults.
