export class DatabaseError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "DatabaseError";
  }
}

export class MigrationError extends DatabaseError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "MigrationError";
  }
}

export class UnsupportedSchemaVersionError extends MigrationError {
  constructor(foundVersion: number, currentVersion: number) {
    super(
      `Unsupported schema version ${foundVersion}. Current app supports ${currentVersion}.`,
    );
    this.name = "UnsupportedSchemaVersionError";
  }
}

export class IntegrityCheckError extends DatabaseError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "IntegrityCheckError";
  }
}

export class ConstraintError extends DatabaseError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ConstraintError";
  }
}

export class UniqueConstraintError extends ConstraintError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "UniqueConstraintError";
  }
}

export class ForeignKeyConstraintError extends ConstraintError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ForeignKeyConstraintError";
  }
}

export class CheckConstraintError extends ConstraintError {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "CheckConstraintError";
  }
}

export function translateSqliteError(error: unknown): DatabaseError {
  if (error instanceof DatabaseError) {
    return error;
  }

  const message = error instanceof Error ? error.message : "Unknown database error";
  const options = error instanceof Error ? { cause: error } : undefined;
  const normalized = message.toLowerCase();

  if (normalized.includes("foreign key")) {
    return new ForeignKeyConstraintError(message, options);
  }

  if (normalized.includes("unique constraint")) {
    return new UniqueConstraintError(message, options);
  }

  if (normalized.includes("check constraint")) {
    return new CheckConstraintError(message, options);
  }

  if (normalized.includes("constraint")) {
    return new ConstraintError(message, options);
  }

  return new DatabaseError(message, options);
}
