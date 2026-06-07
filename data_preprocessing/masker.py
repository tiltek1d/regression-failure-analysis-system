import re
import logging
from typing import List, Any, Dict

logger = logging.getLogger(__name__)

class DataMasker:
    def __init__(self, enabled: bool, sensitive_fields: List[str], keep_start: int, keep_end: int):
        self.enabled = enabled
        self.sensitive_patterns = [re.compile(pattern) for pattern in sensitive_fields]
        # Предопределённые паттерны
        default_patterns = [
            r'unmasked_.*_pan',   # any unmasked_*_pan
            r'client_name',
            r'client_address',
            r'tax_payer_identification_number',
            r'client_passport'
        ]
        self.sensitive_patterns += [re.compile(p) for p in default_patterns]
        self.keep_start = keep_start
        self.keep_end = keep_end

    def mask(self, log_entries: List[Dict]) -> List[Dict]:
        if not self.enabled:
            return log_entries
        return [self._mask_entry(entry) for entry in log_entries]

    def _mask_entry(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._mask_value(k, v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._mask_entry(item) for item in obj]
        else:
            return obj

    def _mask_value(self, key: str, value: Any) -> Any:
        if isinstance(value, str):
            for pattern in self.sensitive_patterns:
                if pattern.fullmatch(key) or pattern.search(key):
                    return self._apply_mask(value)
        elif isinstance(value, (dict, list)):
            return self._mask_entry(value)
        return value

    def _apply_mask(self, s: str) -> str:
        if len(s) <= self.keep_start + self.keep_end:
            return '*' * len(s)
        return s[:self.keep_start] + '*' * (len(s) - self.keep_start - self.keep_end) + s[-self.keep_end:]