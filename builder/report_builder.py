import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from utils.utils import parse_test_name

logger = logging.getLogger(__name__)

DEFAULT_REPORT_TEMPLATE = """Ты получаешь сводный анализ причин расхождений по нескольким тестам регрессии.
Сгруппируй тесты по package (первая часть имени теста) и по тегам причин.
Выдели наиболее частые проблемы, определи системные сбои и бизнес-ошибки.
Выведи итоговый метаанализ. Ответ строго в формате JSON:
{{
  "package_groups": [
    {{
      "package": "имя_пакета",
      "tests": ["test1", "test2"],
      "common_tags": ["tag1", "tag2"],
      "verdict": "краткий вывод по пакету"
    }}
  ],
  "tag_summary": {{
    "имя_тега": {{ "count": 5, "tests": ["test1", "test2"] }}
  }},
  "overall_summary": "Общий вывод по прогону."
}}

Данные для анализа:
{causes_json}
"""


class ReportBuilder:
    """Собирает все результаты анализа причин в единый отчёт, опционально запрашивает LLM для метаанализа."""

    def __init__(self,
                 endpoint: Optional[str] = None,
                 model: Optional[str] = None,
                 timeout: int = 300,
                 prompt_template: Optional[str] = None,
                 send_to_llm: bool = True):
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        self.template = prompt_template or DEFAULT_REPORT_TEMPLATE
        self.send_to_llm = send_to_llm

    def build(self, cause_files: List[Path], output_path: Path) -> Dict[str, Any]:
        """
        Загружает все файлы с причинами, склеивает их в агрегированный JSON,
        и опционально отправляет в LLM для финального отчёта.
        """
        all_data = []
        for cf in cause_files:
            try:
                with open(cf, 'r', encoding='utf-8') as f:
                    all_data.append(json.load(f))
            except Exception as e:
                logger.error(f"Ошибка загрузки файла причин {cf}: {e}")

        aggregated = {
            "total_tests": len(all_data),
            "causes": all_data
        }

        # Сохраняем промежуточный агрегат
        agg_path = output_path.parent / f"{output_path.stem}_aggregated.json"
        with open(agg_path, 'w', encoding='utf-8') as f:
            json.dump(aggregated, f, ensure_ascii=False, indent=2)
        logger.info(f"Агрегированные причины сохранены в {agg_path}")

        if not (self.send_to_llm and self.endpoint and self.model):
            logger.info("Метаанализ LLM отключён или не настроен")
            return aggregated

        prompt = self.template.format(causes_json=json.dumps(aggregated, ensure_ascii=False, indent=2))
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2}
        }

        start = time.time()
        try:
            resp = requests.post(self.endpoint, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            result = resp.json()
            elapsed = time.time() - start
            logger.info(f"Финальный метаанализ выполнен за {elapsed:.1f}с")
            if "response" in result:
                content = result["response"]
                try:
                    final_report = json.loads(content)
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(final_report, f, ensure_ascii=False, indent=2)
                    logger.info(f"Финальный отчёт сохранён в {output_path}")
                    return final_report
                except json.JSONDecodeError:
                    logger.error("Ответ финального метаанализа не содержит JSON, сохраняю как текст")
                    txt_path = output_path.with_suffix('.txt')
                    with open(txt_path, 'w') as f:
                        f.write(content)
                    return {"raw_response": content}
            else:
                raise ValueError(f"Неожиданный ответ: {result}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при финальном запросе: {e}")
            return aggregated