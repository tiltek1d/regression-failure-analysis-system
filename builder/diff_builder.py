from typing import List, Dict, Any

class DiffBuilder:
    def build(self, test_name: str, task_comparisons: List[Dict], unmatched_etalon: List, unmatched_test: List) -> Dict:
        """
        task_comparisons: список результатов сравнения пар задач по порядку.
        Каждый элемент имеет вид:
        {
            "task_index": int,
            "etalon_task_id": any,
            "test_task_id": any,
            "comparison": { ... }   # результат от LLM (с ключом "operations")
        }
        unmatched_etalon: список task_id эталона, для которых нет пары
        unmatched_test: список task_id теста, для которых нет пары
        """
        tasks_report = []
        for comp in task_comparisons:
            tasks_report.append({
                "task_index": comp["task_index"],
                "etalon_task_id": comp["etalon_task_id"],
                "test_task_id": comp["test_task_id"],
                "operations": comp["comparison"].get("operations", [])
            })

        # добавление непарных задач
        for et_id in unmatched_etalon:
            tasks_report.append({
                "task_index": len(tasks_report),
                "etalon_task_id": et_id,
                "test_task_id": None,
                "operations": [],
                "status": "unmatched_etalon"
            })
        for test_id in unmatched_test:
            tasks_report.append({
                "task_index": len(tasks_report),
                "etalon_task_id": None,
                "test_task_id": test_id,
                "operations": [],
                "status": "unmatched_test"
            })

        return {
            "test_name": test_name,
            "tasks": tasks_report,
            "unmatched_etalon_tasks": unmatched_etalon,
            "unmatched_test_tasks": unmatched_test,
            "summary": {
                "total_tasks_compared": len(task_comparisons),
                "total_operations": sum(len(t["operations"]) for t in tasks_report if "operations" in t),
                "unmatched_etalon_count": len(unmatched_etalon),
                "unmatched_test_count": len(unmatched_test)
            }
        }