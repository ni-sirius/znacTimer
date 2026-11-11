import { Directory, File, FileMode, Paths } from "expo-file-system";
import * as SQLite from "expo-sqlite";

import { inspectDatabase, isSupportedDatabase, type DatabaseCheck } from "./inspectDatabase";
import type { BackupTarget, MonthExportPeriod } from "./repository.types";
import { exportMonthKey, monthExportProblem, retainExportPeriod } from "./exportPeriod";

function temporaryDirectory(): Directory {
  const directory = new Directory(Paths.cache, `znactime-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  directory.create();
  return directory;
}

function removeDatabaseFiles(file: File) {
  for (const suffix of ["", "-wal", "-shm", "-journal"]) {
    const part = new File(file.uri + suffix);
    if (part.exists) part.delete();
  }
}

/** Snapshot the live database through SQLite, including committed WAL data. */
export async function backupTo(source: SQLite.SQLiteDatabase, target: BackupTarget): Promise<void> {
  if (target.period) {
    const problem = monthExportProblem(target.period);
    if (problem) throw new Error(problem);
  }
  const file = new File(target.uri);
  const sourceUri = source.databasePath.startsWith("file:") ? source.databasePath : `file://${source.databasePath}`;
  if (["", "-wal", "-shm", "-journal"].some((suffix) => new File(sourceUri + suffix).uri === file.uri)) {
    throw new Error("Choose a backup destination outside the active database files.");
  }
  if (file.exists) throw new Error("The backup destination already exists.");
  let destination: SQLite.SQLiteDatabase | undefined;
  let reader: SQLite.SQLiteDatabase | undefined;
  try {
    const sourceFile = new File(sourceUri);
    // A separate reader sees committed data, even while the app is saving in WAL mode.
    reader = await SQLite.openDatabaseAsync(sourceFile.name, { useNewConnection: true }, sourceFile.parentDirectory.uri);
    destination = await SQLite.openDatabaseAsync(file.name, { useNewConnection: true }, file.parentDirectory.uri);
    await SQLite.backupDatabaseAsync({ sourceDatabase: reader, destDatabase: destination });
    // Publish one standalone file, without a companion WAL.
    await destination.execAsync("PRAGMA journal_mode = DELETE");
    if (target.period) await retainExportPeriod(destination, target.period);
    const result = await inspectDatabase(destination);
    if (!isSupportedDatabase(result)) throw new Error(result.message);
    await destination.closeAsync();
    destination = undefined;
  } catch (error) {
    if (destination) await destination.closeAsync();
    removeDatabaseFiles(file);
    throw error;
  } finally {
    if (reader) await reader.closeAsync();
  }
}

export function databaseBackupName(date = new Date(), period?: MonthExportPeriod): string {
  const part = (value: number) => String(value).padStart(2, "0");
  const range = period ? `${exportMonthKey(period.from)}_${exportMonthKey(period.to)}-` : "";
  return `znactime-backup-${range}${date.getFullYear()}${part(date.getMonth() + 1)}${part(date.getDate())}-${part(date.getHours())}${part(date.getMinutes())}${part(date.getSeconds())}.db`;
}

export async function exportDatabase(source: SQLite.SQLiteDatabase, period?: MonthExportPeriod): Promise<void> {
  const Sharing = await import("expo-sharing");
  if (!await Sharing.isAvailableAsync()) throw new Error("File sharing is unavailable on this device.");
  const directory = temporaryDirectory();
  let shared = false;
  try {
    const file = new File(directory, databaseBackupName(new Date(), period));
    // Use the repository API so every export follows the same snapshot rules.
    const { createRepository } = await import("./repository");
    await createRepository(source).backupTo({ uri: file.uri, period });
    await Sharing.shareAsync(file.uri, { mimeType: "application/vnd.sqlite3", UTI: "public.database", dialogTitle: "Export SQLite" });
    shared = true;
  } finally {
    // Android recipients may read the file after the share sheet has closed.
    // Successful exports stay in the OS-managed cache until it is cleaned.
    if (!shared && directory.exists) directory.delete();
  }
}

/** Inspect an isolated copy. Neither the selected file nor the live database is changed. */
export async function checkDatabaseFile(uri: string): Promise<DatabaseCheck> {
  const directory = temporaryDirectory();
  const copy = new File(directory, "inspection.db");
  let database: SQLite.SQLiteDatabase | undefined;
  try {
    await new File(uri).copy(copy);
    if (copy.size === 0) return { code: "empty", message: "The selected file is empty." };
    const handle = copy.open(FileMode.ReadOnly);
    let header: Uint8Array;
    try { header = await handle.readBytes(16); }
    finally { handle.close(); }
    if (Array.from(header, (value) => String.fromCharCode(value)).join("") !== "SQLite format 3\0") {
      return { code: "not-sqlite", message: "The selected file is not a readable SQLite database." };
    }
    database = await SQLite.openDatabaseAsync(copy.name, { useNewConnection: true }, directory.uri);
    await database.execAsync("PRAGMA query_only = ON; PRAGMA trusted_schema = OFF;");
    return await inspectDatabase(database);
  } catch (error) {
    if (!database && copy.exists && copy.size > 0) return { code: "corrupt", message: "The selected SQLite file is damaged or could not be opened." };
    throw error;
  } finally {
    try { if (database) await database.closeAsync(); }
    finally { if (directory.exists) directory.delete(); }
  }
}
