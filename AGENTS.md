# Repository Guidelines

## Project Structure & Module Organization

`opencore_legacy_patcher/` contains the Python application. Keep OpenCore configuration generation in `efi_builder/`, root-volume patching in `sys_patch/`, hardware detection in `detections/`, model tables and fixtures in `datasets/`, shared utilities and validation in `support/`, and wxPython screens in `wx_gui/`. `payloads/` holds bundled OpenCore components, kexts, ACPI tables, configuration templates, and icons. `ci_tooling/` contains packaging scripts and the Objective-C privileged helper. Documentation lives in `docs/`; start with `SOURCE.md` for development setup. GitHub Actions workflows live in `.github/workflows/`.

## Build, Test, and Development Commands

Run commands from the repository root on macOS. Use a Python installation from python.org; `SOURCE.md` identifies system and Xcode Python installations as unsupported. Release builds use Python 3.11.

- `python3 -m pip install -r requirements.txt`: install application and packaging dependencies.
- `python3 OpenCore-Patcher-GUI.command`: launch the GUI from source.
- `python3 OpenCore-Patcher-GUI.command --build --model iMac12,2 --verbose`: generate an OpenCore configuration for a specific model.
- `python3 OpenCore-Patcher-GUI.command --validate`: run the repository’s CI validation suite.
- `python3 Build-Project.command`: prepare assets and generate application and installer artifacts under `dist/`.

## Coding Style & Naming Conventions

Follow surrounding Python code: four-space indentation, `snake_case` modules and functions, `PascalCase` classes, descriptive docstrings, and type annotations for function interfaces. Preserve established hardware identifiers such as `MacBookPro13,3`. Keep hardware-specific decisions in the relevant builder, detection, or patchset module. Flake8 and Pylint configurations are provided in `.flake8` and `.pylintrc`; Flake8 ignores E501 and E203. Avoid unrelated formatting changes.

## Testing Guidelines

Testing uses the custom `PatcherValidation` suite in `support/validation.py`. It generates configurations for supported models and hardware fixtures, checks them with bundled `ocvalidate`, and validates root-patch payloads. Extend `datasets/example_data.py` and the validator when adding hardware cases; follow existing model-based fixture names. No numeric coverage threshold is configured. Run `--validate` before submitting functional changes, and record affected Mac models, macOS versions, and manual GUI or hardware checks.

## Commit & Pull Request Guidelines

Recent commits use short, imperative subjects such as “Fix the Skylake patches on Tahoe” and “Update Kexts and OpenCore.” Keep commits focused. PR descriptions should explain the problem, affected models and OS versions, resulting behavior, and validation performed. Link related issues and include screenshots for visible GUI changes. Explain payload updates and their upstream provenance when replacing bundled binaries.
