"""Общие утилиты для всего проекта."""

import re
from typing import Optional, Tuple


def parse_test_name(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Извлекает имя теста и опциональную дату из имени файла.
    Ожидаемый формат: log_<package>_<test_name>_<date>.json
    Возвращает (test_name, date_str) или (None, None) при несоответствии.
    """
    if not filename.endswith('.json'):
        return None, None
    name_no_ext = filename[:-5]
    parts = name_no_ext.split('_')
    if len(parts) < 3 or parts[0] != 'log':
        return None, None
    date_str = parts[-1]
    if not all(c.isdigit() or c == '-' for c in date_str):
        test_name = '_'.join(parts[1:])
        date_str = None
    else:
        test_name = '_'.join(parts[1:-1])
    return test_name, date_str