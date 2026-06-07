import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_CAUSE_TEMPLATE = """Ты анализируешь результаты сравнения тестового прогона с эталоном.
Ниже представлен файл различий по одному тесту.
На основе этих различий определи возможные причины расхождений и присвой теги каждому различию.
Теги должны быть из следующего списка (можно добавлять новые):
- system_malfunction: ошибка на уровне инфраструктуры (проблемы с БД, Kafka topic не найден, 500/503 ошибки, таймауты)
- business_config_error: ошибка бизнес-конфигурации (устройство не разрешено, коды 57/58, не настроен сервис эквайринга/эмиссии, неверный BIN)
- data_mismatch: несовпадение данных (ожидалось одно значение, получено другое)
- missing_service: отсутствует вызов сервиса (сервис не был вызван или вызван другой)
- other: прочее

Для каждого различия укажи:
- operation_index: номер операции внутри задачи (начиная с 0)
- service_name (если известно)
- cause: краткое описание причины
- tags: список тегов (массив строк)

Также дай общий вердикт по тесту: основные проблемы и вероятная первопричина.
Ответ строго в формате JSON:
{{
  "test_name": "<имя теста>",
  "causes": [
    {{
      "task_index": 0,
      "etalon_task_id": "...",
      "test_task_id": "...",
      "operations": [
        {{
          "operation_index": 0,
          "service_name": "...",
          "cause": "...",
          "tags": ["system_malfunction"]
        }}
      ]
    }}
  ],
  "overall_verdict": "Краткий вывод."
}}

Данные для анализа:
{diff_json}
"""


class LLMCauseAnalyzer:
    """Отправляет diff-файл в LLM для анализа причин и присвоения тегов."""

    def __init__(self, endpoint: str, model: str, timeout: int = 300,
                 prompt_template: Optional[str] = None):
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        self.template = prompt_template or DEFAULT_CAUSE_TEMPLATE

    def analyze(self, diff_file: Path) -> Dict[str, Any]:
        """Анализирует diff-файл и возвращает словарь с причинами."""
        with open(diff_file, 'r', encoding='utf-8') as f:
            diff_data = json.load(f)

        test_name = diff_data.get("test_name", diff_file.stem)
        prompt = self.template.format(diff_json=json.dumps(diff_data, ensure_ascii=False, indent=2))

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2}
        }

        start = time.time()
        try:
            response = requests.post(self.endpoint, json=payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            elapsed = time.time() - start
            logger.info(f"Анализ причин для {test_name} выполнен за {elapsed:.1f}с")
            if "response" in result:
                content = result["response"]
                try:
                    parsed = json.loads(content)
                    parsed.setdefault("test_name", test_name)
                    return parsed
                except json.JSONDecodeError:
                    logger.warning(f"Ответ анализа причин не JSON: {content[:100]}")
                    return {"test_name": test_name, "raw_response": content, "error": "JSON parse error"}
            else:
                raise ValueError(f"Неожиданный формат ответа LLM: {result}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса анализа причин для {test_name}: {e}")
            raise