import os

from znactime.config import DATA_DIR


def _data_dir(data_dir=None):
    return DATA_DIR if data_dir is None else data_dir


def year_dir(year, create=False, data_dir=None):
    path = os.path.join(_data_dir(data_dir), str(year))
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def tmp_month_file(year, month, data_dir=None):
    return os.path.join(
        year_dir(year, data_dir=data_dir),
        f"{year}_tmp_{month:02}.csv",
    )


def closed_flag_file(year, month, data_dir=None):
    return os.path.join(
        year_dir(year, data_dir=data_dir),
        f"closed_{month:02}.flag",
    )


def year_summary_file(year, data_dir=None):
    return os.path.join(
        year_dir(year, data_dir=data_dir),
        f"{year}.csv",
    )
