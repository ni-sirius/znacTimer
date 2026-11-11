import type { SQLiteDatabase } from "expo-sqlite";
import { writeTransaction } from "./transactions";

// Web does not support exclusive SQLite transactions.
export async function monthTransaction<T>(
  db: SQLiteDatabase,
  operation: (transaction: SQLiteDatabase) => Promise<T>,
): Promise<T> {
  return writeTransaction(db, () => operation(db));
}
