import type { SQLiteDatabase } from "expo-sqlite";

const pendingTransactions = new WeakMap<SQLiteDatabase, Promise<void>>();

// Expo's isolated transaction connections still share one SQLite writer.
export function serializeTransaction<T>(db: SQLiteDatabase, operation: () => Promise<T>): Promise<T> {
  const previous = pendingTransactions.get(db) ?? Promise.resolve();
  const result = previous.then(operation);
  const settled = result.then(() => {}, () => {});
  pendingTransactions.set(db, settled);
  void settled.then(() => {
    if (pendingTransactions.get(db) === settled) pendingTransactions.delete(db);
  });
  return result;
}
