"""Core package for the skill-learner thesis pipeline."""

from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "skill-learner"

try:
    __version__ = version(PACKAGE_NAME)
except PackageNotFoundError:
    # Fallback for local runs before editable install metadata is available.
    __version__ = "0.1.0"

__all__ = ["PACKAGE_NAME", "__version__"]
