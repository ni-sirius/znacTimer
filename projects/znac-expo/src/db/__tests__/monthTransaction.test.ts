import { describe, expect, it, vi } from "vitest";
import { openDatabaseAsync } from "expo-sqlite";
import { monthTransaction } from "../monthTransaction.native";

vi.mock("expo-sqlite", () => ({ openDatabaseAsync: vi.fn() }));

describe("native month transaction", () => {
  it("enables foreign keys before beginning on a separate connection and closes it", async () => {
    const tx = { execAsync: vi.fn(), closeAsync: vi.fn(), runAsync: vi.fn() };
    vi.mocked(openDatabaseAsync).mockResolvedValueOnce(tx as never);
    const db = { databasePath: "/app/SQLite/znactime.db", runAsync: vi.fn() };
    expect(await monthTransaction(db as never, async (connection) => { await connection.runAsync("SELECT 1"); return 7; })).toBe(7);
    expect(openDatabaseAsync).toHaveBeenLastCalledWith("znactime.db", { useNewConnection: true }, "/app/SQLite");
    expect(tx.execAsync.mock.calls.map(([sql]) => sql)).toEqual(["PRAGMA foreign_keys = ON;", "BEGIN IMMEDIATE;", "COMMIT;"]);
    expect(tx.closeAsync).toHaveBeenCalledOnce();
    expect(db.runAsync).not.toHaveBeenCalled();
  });

  it("rolls back a failed operation and releases the connection", async () => {
    const tx = { execAsync: vi.fn(), closeAsync: vi.fn() };
    vi.mocked(openDatabaseAsync).mockResolvedValueOnce(tx as never);
    const failure = new Error("write failed");
    await expect(monthTransaction({ databasePath: "/app/test.db" } as never, async () => { throw failure; })).rejects.toBe(failure);
    expect(tx.execAsync).toHaveBeenLastCalledWith("ROLLBACK;");
    expect(tx.closeAsync).toHaveBeenCalledOnce();
  });
});
