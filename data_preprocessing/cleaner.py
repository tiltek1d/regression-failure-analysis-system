import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class LogCleaner:
    def __init__(self, remove_fields: List[str], kafka_keep_levels: List[str], clickhouse_keep_levels: List[str]):
        self.remove_fields = set(remove_fields)
        self.kafka_keep_levels = set(level.upper() for level in kafka_keep_levels)
        self.clickhouse_keep_levels = set(level.upper() for level in clickhouse_keep_levels)
        # специфичные сервисы для фильтрации по уровню
        self.special_services = {
            'KAFKA': self.kafka_keep_levels,
            'clickhouse-consumer': self.clickhouse_keep_levels
        }

    def clean(self, log_entries: List[Dict]) -> List[Dict]:
        cleaned = []
        for entry in log_entries:
            if not isinstance(entry, dict):
                logger.warning(f"Запись не словарь, пропущена: {entry}")
                continue
            # Удаляем запись, если это KAFKA/clickhouse-consumer и уровень не соответствует
            if self._should_remove(entry):
                continue
            # Рекурсивно удаляем неинформативные поля
            cleaned_entry = self._remove_fields(entry)
            cleaned.append(cleaned_entry)
        logger.info(f"Удалено записей: {len(log_entries) - len(cleaned)}")
        return cleaned

    def _should_remove(self, entry: Dict) -> bool:
        service = entry.get('service_name')
        if service in self.special_services:
            level = entry.get('level', '').upper()
            keep_levels = self.special_services[service]
            if level not in keep_levels:
                return True
        return False

    def _remove_fields(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            new_dict = {}
            for k, v in obj.items():
                if k in self.remove_fields:
                    continue
                new_dict[k] = self._remove_fields(v)
            return new_dict
        elif isinstance(obj, list):
            return [self._remove_fields(item) for item in obj]
        else:
            return obj