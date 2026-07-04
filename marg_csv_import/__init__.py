"""marg-csv-import — parse stock CSV exports from Indian pharmacy
desktop software (Marg ERP, eVitalRx, Vyapar) into normalized dicts.
"""

from .parser import detect_columns, parse_csv, parse_expiry

__all__ = ["parse_csv", "detect_columns", "parse_expiry"]
__version__ = "0.1.0"
