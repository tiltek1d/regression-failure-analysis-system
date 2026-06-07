import json
import logging
import time
import requests
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = """Ты анализируешь один task тестового прогона в сравнении с эталонным.
Эталонный прогон (task ID: {etalon_task_id}):
{etalon_log}

Тестовый прогон (task ID: {test_task_id}):
{test_log}

Внутри одного task может быть несколько вызовов различных сервисов. Для каждого вызова определи:
- service_name
- service_version
- expectation: что ожидалось в поле data (из эталона)
- reality: что фактически пришло в тестовом прогоне
- различия (если есть)

Ответь строго в формате JSON:
{{
  "operations": [
    {{
      "service_name": "...",
      "service_version": "...",
      "expectation": {{ ... }},
      "reality": {{ ... }},
      "differences": ["описание различия", ...]
    }}
  ]
}}
"""

class LLMComparatorClient:
    def __init__(self, endpoint: str, model: str, timeout: int = 300, prompt_template: Optional[str] = None):
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        self.template = prompt_template or DEFAULT_TEMPLATE

    def compare_tasks(self, etalon_task_id: Any, test_task_id: Any,
                      etalon_log: List[Dict], test_log: List[Dict]) -> Dict:
        etalon_str = json.dumps(etalon_log, ensure_ascii=False, indent=2)
        test_str = json.dumps(test_log, ensure_ascii=False, indent=2)
        prompt = self.template.format(
            etalon_task_id=etalon_task_id,
            test_task_id=test_task_id,
            etalon_log=etalon_str,
            test_log=test_str
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1}
        }
        start = time.time()
        try:
            response = requests.post(self.endpoint, json=payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            elapsed = time.time() - start
            logger.info(f"LLM запрос для пары task (etalon={etalon_task_id}, test={test_task_id}) выполнен за {elapsed:.1f}с")
            if "response" in result:
                content = result["response"]
                try:
                    parsed = json.loads(content)
                    if "operations" not in parsed:
                        # на случай, если LLM вернула не тот формат – обернём
                        logger.warning("Ответ LLM не содержит 'operations', оборачиваем в структуру")
                        parsed = {"operations": [parsed]}
                    return parsed
                except json.JSONDecodeError:
                    logger.warning(f"Ответ LLM не JSON: {content[:100]}")
                    return {"operations": [], "raw_response": content}
            else:
                raise ValueError(f"Неожиданный формат ответа LLM: {result}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ошибка запроса к LLM: {e}") from e