import { openDatabaseAsync, type SQLiteDatabase } from "expo-sqlite";
import { serializeTransaction } from "./transactionQueue";

// Configure foreign keys before BEGIN: SQLite cannot enable them inside an active transaction.
export async function monthTransaction<T>(db: SQLiteDatabase, operation: (transaction: SQLiteDatabase) => Promise<T>): Promise<T> {
  return serializeTransaction(db, async () => {
    const path = db.databasePath.replace(/\\/g, "/");
    const separator = path.lastIndexOf("/");
    const transaction = await openDatabaseAsync(path.slice(separator + 1), { useNewConnection: true }, path.slice(0, separator));
    let active = false;
    try {
      await transaction.execAsync("PRAGMA foreign_keys = ON;");
      await transaction.execAsync("BEGIN IMMEDIATE;");
      active = true;
      const result = await operation(transaction);
      await transaction.execAsync("COMMIT;");
      active = false;
      return result;
    } catch (error) {
      if (active) await transaction.execAsync("ROLLBACK;");
      throw error;
    } finally { await transaction.closeAsync(); }
  });
}
