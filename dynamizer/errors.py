class DynomizerError(Exception):
    pass


class UnsupportedTypeError(DynomizerError):
    pass


class ConcurrentUpdateError(DynomizerError):
    """The model changed since reading."""