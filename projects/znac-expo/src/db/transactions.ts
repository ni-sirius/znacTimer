import type * as SQLite from "expo-sqlite";
import { serializeTransaction } from "./transactionQueue";

export async function readTransaction<T>(
  db: SQLite.SQLiteDatabase,
  operation: () => Promise<T>,
): Promise<T> {
  return serializeTransaction(db, async () => {
    let result!: T;
    await db.withTransactionAsync(async () => {
      result = await operation();
    });
    return result;
  });
}

export async function writeTransaction<T>(
  db: SQLite.SQLiteDatabase,
  operation: () => Promise<T>,
): Promise<T> {
  return readTransaction(db, operation);
}
