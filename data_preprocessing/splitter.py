import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class TaskSplitter:
    def __init__(self, task_field: str = 'task_id', preserve_order: bool = True):
        self.task_field = task_field
        self.preserve_order = preserve_order

    def split(self, log_entries: List[Dict]) -> List[Tuple[Any, List[Dict]]]:
        """
        Группирует записи по task_id, сохраняя порядок первого появления.
        Возвращает список кортежей: (task_id, [записи]).
        """
        tasks = []
        seen_ids = set()
        index_map = {}  # task_id -> index in tasks

        for entry in log_entries:
            if not isinstance(entry, dict):
                continue
            task_id = entry.get(self.task_field)
            if task_id is None:
                logger.debug(f"Запись без поля {self.task_field}, пропущена: {entry.get('message', '')[:50]}")
                continue
            if task_id not in seen_ids:
                seen_ids.add(task_id)
                tasks.append((task_id, []))
                index_map[task_id] = len(tasks) - 1
            tasks[index_map[task_id]][1].append(entry)
        return tasks