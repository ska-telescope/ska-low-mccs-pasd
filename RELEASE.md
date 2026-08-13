# Release Process

For version bumps, always update:
- pyproject.toml (version field)
- uv.lock (by running 'uv lock')
- src/ska_low_mccs_pasd/__init__.py
- CHANGELOG.md
- .release (both release and tag)
- charts/ska-low-mccs-pasd/Chart.yaml (version and appVersion)
- charts/ska-low-mccs-pasd/values.yaml (tag in both places)

Note: CHANGELOG.md must be updated with a note describing the change set
under the heading 'Unreleased' if the MR does not include a version bump.