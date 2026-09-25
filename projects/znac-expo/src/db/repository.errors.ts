export class RepositoryError extends Error {}

export class RevisionConflictError extends RepositoryError {
  constructor() {
    super("The record was changed by another operation.");
    this.name = "RevisionConflictError";
  }
}

export class ClosedMonthError extends RepositoryError {
  constructor() {
    super("Closed month cannot be edited.");
    this.name = "ClosedMonthError";
  }
}

export class MonthNotFoundError extends RepositoryError {
  constructor() {
    super("Month was not found.");
    this.name = "MonthNotFoundError";
  }
}

export class DayNotFoundError extends RepositoryError {
  constructor() {
    super("Day was not found.");
    this.name = "DayNotFoundError";
  }
}

export class InvalidWorkdayTransitionError extends RepositoryError {
  constructor(message = "Workday action is not valid for the current state.") {
    super(message);
    this.name = "InvalidWorkdayTransitionError";
  }
}
