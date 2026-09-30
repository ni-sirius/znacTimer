import {
  ClosedMonthError,
  RevisionConflictError,
} from "../db/repository.errors";

export function storeErrorMessage(error: unknown): string {
  if (error instanceof RevisionConflictError) {
    return "Record was changed elsewhere. Reload and try again.";
  }

  if (error instanceof ClosedMonthError) {
    return "Closed month cannot be edited.";
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Unexpected error.";
}
