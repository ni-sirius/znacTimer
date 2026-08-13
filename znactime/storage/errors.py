class StorageError(Exception):
    """Base class for stable persistence errors exposed outside storage adapters."""


class StorageUnavailable(StorageError):
    pass


class StorageLocked(StorageError):
    pass


class StorageCorrupt(StorageError):
    pass


class StorageVersionUnsupported(StorageError):
    pass


class StorageValidationError(StorageError):
    pass


class StorageConflict(StorageError):
    pass


class ClosedPeriodError(StorageError):
    pass
