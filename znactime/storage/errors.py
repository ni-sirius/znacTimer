class StorageError(Exception):
    """Base class for stable persistence errors exposed outside storage adapters."""


class StorageUnavailable(StorageError):
    pass


class StorageLocked(StorageError):
    pass


class ApplicationAlreadyRunning(StorageLocked):
    """A second application process targeted the same local database."""


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
