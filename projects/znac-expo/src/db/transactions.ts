import * as SQLite from "expo-sqlite";

export async function readTransaction<T>(
  db: SQLite.SQLiteDatabase,
  operation: () => Promise<T>,
): Promise<T> {
  let result: T | undefined;

  await db.withTransactionAsync(async () => {
    result = await operation();
  });

  return result as T;
}

export async function writeTransaction<T>(
  db: SQLite.SQLiteDatabase,
  operation: () => Promise<T>,
): Promise<T> {
  let result: T | undefined;

  await db.withTransactionAsync(async () => {
    result = await operation();
  });

  return result as T;
}
