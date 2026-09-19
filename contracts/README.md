# Shared contracts

This directory is reserved for behavior and data-format contracts used by more
than one znacTime implementation. It does not contain shared executable code.

- [`schemas/`](schemas/README.md): versioned exchange-format definitions when needed.
- [`fixtures/`](fixtures/README.md): synthetic inputs and expected results for
  calculations, breaks, month closing, and carry-over.

The existing [database dictionary](../docs/DATABASE_SCHEMA.md) describes znacpy's
current SQLite storage. Cross-project contracts will be defined when another
implementation needs them; this layout does not introduce synchronization.
