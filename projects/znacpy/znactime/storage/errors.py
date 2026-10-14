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


class DatabaseVersionTooNew(StorageVersionUnsupported):
    def __init__(self, database_version: int, supported_version: int):
        self.database_version = database_version
        self.supported_version = supported_version
        super().__init__(
            f"Database version {database_version} is newer than the supported "
            f"version {supported_version}."
        )


class StorageValidationError(StorageError):
    pass


class ExportError(StorageError):
    pass


class StorageConflict(StorageError):
    pass


class ClosedPeriodError(StorageError):
    pass
