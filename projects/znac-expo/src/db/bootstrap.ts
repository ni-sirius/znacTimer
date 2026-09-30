import * as SQLite from "expo-sqlite";

import { getDatabase } from "./connection";
import { migrateDatabase } from "./migrations";

export async function initializeDatabase(): Promise<SQLite.SQLiteDatabase> {
  const db = await getDatabase();

  await migrateDatabase(db);

  return db;
}
