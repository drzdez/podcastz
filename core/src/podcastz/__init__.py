"""podcastz: dialogue scripts -> podcast audio. Library used by the CLI and the app backend."""

__version__ = '0.1.0'


class PodcastzError(Exception):
    """User-facing error (bad project, missing key, unknown model...)."""
