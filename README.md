# znacTime

A local-first time tracker, organized as independently maintained projects.

| Project | Status |
| --- | --- |
| [znacpy](projects/znacpy/README.md) | Existing Python implementation using PySide6 and SQLite. |
| [otherplatform](projects/otherplatform/README.md) | Placeholder for a future implementation; no framework selected. |

## Repository layout

```text
projects/
  znacpy/          Python source, tests, dependencies, utilities, and local files
  otherplatform/  Future implementation placeholder
contracts/        Shared specifications and cross-implementation examples
docs/             Architecture, database documentation, images, and project plans
scripts/          Repository-wide release checks
```

Each project owns its dependencies, development environment, tests, and release
version. Shared contracts can evolve as another implementation is developed.
There is no JavaScript workspace or dependency setup yet.

## Run znacpy

From the repository root on Windows with Python 3.12:

```powershell
cd projects/znacpy
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m znactime
```

If a working `.venv` already exists in the project, use it directly. See the
[znacpy README](projects/znacpy/README.md) for features, data handling, testing,
and development commands. Open `projects/znacpy` in VS Code to use its project
settings.

Local environments, legacy data, build output, and caches belong inside their
project and are ignored by Git. The existing per-user SQLite database location
is independent of this repository layout.

## Repository checks

From the repository root:

```powershell
.\projects\znacpy\.venv\Scripts\python.exe -m unittest discover -s projects/znacpy/tests -t projects/znacpy -v
.\projects\znacpy\.venv\Scripts\python.exe scripts/check_release_tree.py --working-tree
```

The working-tree check includes existing tracked files and non-ignored new files,
so it can validate changes before staging. Before a release, also run the check
without `--working-tree` to validate the Git index. Release tags can be scoped by
project, for example `znacpy/v0.6.1`; existing tags remain valid.

## Documentation

- [Functional requirements](docs/architecture/FUNCTIONAL_REQUIREMENTS.md)
- [SQLite database dictionary](docs/DATABASE_SCHEMA.md)
- [znacpy migration and release plan](docs/projects/znacpy/MIGRATION_PLAN.md)
- [znacpy SQLite migration plan](docs/projects/znacpy/SQLITE_MIGRATION_PLAN.md)
- [Shared contracts](contracts/README.md)

znacTime is available under the [MIT License](LICENSE). Dependency notices are
maintained by each project: [znacpy notices](projects/znacpy/THIRD_PARTY_NOTICES.md).
