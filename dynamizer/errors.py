class DynomizerError(Exception):
    pass


class UnsupportedTypeError(DynomizerError):
    pass


class ConcurrentUpdateError(DynomizerError):
    """The model changed since reading."""


class ModelNotFoundError(DynomizerError):
    """The model class could not be identified."""


class UnsupportedStreamModeError(DynomizerError):
    """The stream mode is not supported."""
