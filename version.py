"""Single source of truth for the application version.

This value is read by:
* ``/api/version`` and ``/api/backends`` (so the UI can render it)
* ``updater.check_for_update`` (so it can compare against the latest GitHub
  release tag)
* PyInstaller specs via build-time string substitution if/when needed.

Bump this before tagging a release.
"""

__version__ = "1.2.0"