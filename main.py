import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from tqdm import tqdm

from data_preprocessing.cleaner import LogCleaner
from data_preprocessing.masker import DataMasker
from data_preprocessing.splitter import TaskSplitter
from clients.llm_client import LLMComparatorClient
from clients.llm_cause_analyzer import LLMCauseAnalyzer
from builder.diff_builder import DiffBuilder
from builder.report_builder import ReportBuilder
from utils.utils import parse_test_name

# Настройка логирования
def setup_logging(level: str):
    logger = logging.getLogger()
    logger.setLevel(level.upper())
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def load_config(config_path: str) -> dict:
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def find_file_pairs(test_dir: str, etalon_dir: str, package_filter: Optional[str] = None) -> List[Tuple[str, Path, Path]]:
    test_path = Path(test_dir)
    etalon_path = Path(etalon_dir)
    if not test_path.is_dir():
        raise FileNotFoundError(f"Директория тестов не найдена: {test_dir}")
    if not etalon_path.is_dir():
        raise FileNotFoundError(f"Директория эталонов не найдена: {etalon_dir}")

    test_files = {}
    etalon_files = {}

    for f in test_path.glob('*.json'):
        name, _ = parse_test_name(f.name)
        if not name:
            logging.warning(f"Не удалось извлечь имя теста из {f.name}")
            continue
        if package_filter and package_filter not in name:
            continue
        if name in test_files:
            logging.warning(f"Дубликат теста {name}, используется последний")
        test_files[name] = f

    for f in etalon_path.glob('*.json'):
        name, _ = parse_test_name(f.name)
        if not name:
            logging.warning(f"Не удалось извлечь имя теста из эталона {f.name}")
            continue
        if package_filter and package_filter not in name:
            continue
        if name in etalon_files:
            logging.warning(f"Дубликат эталона {name}, используется последний")
        etalon_files[name] = f

    pairs = []
    for name, tf in test_files.items():
        if name in etalon_files:
            pairs.append((name, tf, etalon_files[name]))
        else:
            logging.warning(f"Для теста {name} не найден эталон")
    for name in etalon_files:
        if name not in test_files:
            logging.warning(f"Для эталона {name} нет тестового файла")
    return pairs


def load_json(file_path: Path) -> List[Dict]:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return v
        raise ValueError(f"Файл {file_path} не содержит список логов")
    return data


def process_test(test_name: str, test_file: Path, etalon_file: Path,
                 cleaner: LogCleaner, masker: DataMasker,
                 splitter: TaskSplitter, llm: LLMComparatorClient,
                 diff_builder: DiffBuilder, output_dir: Path) -> Optional[Path]:
    start_time = time.time()
    logging.info(f"=== Обработка теста: {test_name} ===")
    try:
        test_log = load_json(test_file)
        etalon_log = load_json(etalon_file)
        logging.info(f"Загружено записей: тест {len(test_log)}, эталон {len(etalon_log)}")

        test_clean = cleaner.clean(test_log)
        etalon_clean = cleaner.clean(etalon_log)
        logging.info(f"После очистки: тест {len(test_clean)}, эталон {len(etalon_clean)}")

        test_masked = masker.mask(test_clean)
        etalon_masked = masker.mask(etalon_clean)

        # Получаем упорядоченные списки задач
        test_tasks = splitter.split(test_masked)   # list of (task_id, [entries])
        etalon_tasks = splitter.split(etalon_masked)
        logging.info(f"Найдено task: тест {len(test_tasks)}, эталон {len(etalon_tasks)}")

        max_len = max(len(test_tasks), len(etalon_tasks))
        task_comparisons = []
        unmatched_etalon = []
        unmatched_test = []

        # Проходим по индексам задач
        for idx in tqdm(range(max_len), desc=f"Tasks {test_name}", unit="pair"):
            if idx < len(etalon_tasks):
                et_id, et_entries = etalon_tasks[idx]
            else:
                et_id, et_entries = None, None

            if idx < len(test_tasks):
                test_id, test_entries = test_tasks[idx]
            else:
                test_id, test_entries = None, None

            if et_entries is None and test_entries is None:
                continue

            # Ситуация: задача только в эталоне
            if test_entries is None:
                unmatched_etalon.append(et_id)
                continue
            # Ситуация: задача только в тесте
            if et_entries is None:
                unmatched_test.append(test_id)
                continue

            # Обе задачи есть – вызываем LLM
            try:
                comparison = llm.compare_tasks(et_id, test_id, et_entries, test_entries)
                task_comparisons.append({
                    "task_index": idx,
                    "etalon_task_id": et_id,
                    "test_task_id": test_id,
                    "comparison": comparison
                })
            except Exception as e:
                logging.error(f"Ошибка сравнения пары task (etalon={et_id}, test={test_id}): {e}")
                task_comparisons.append({
                    "task_index": idx,
                    "etalon_task_id": et_id,
                    "test_task_id": test_id,
                    "comparison": {"operations": [], "error": str(e)}
                })

        # Сборка итогового diff
        result = diff_builder.build(
            test_name,
            task_comparisons,
            unmatched_etalon,
            unmatched_test
        )

        output_path = output_dir / f"log_{test_name}_diff.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        elapsed = time.time() - start_time
        logging.info(f"Тест {test_name} готов за {elapsed:.1f} с -> {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"Критическая ошибка при обработке {test_name}: {e}", exc_info=True)
        return None

def main():
    parser = argparse.ArgumentParser(description='Анализатор развала регрессии (полный цикл)')
    parser.add_argument('--config', default='settings.yaml', help='Путь к YAML конфигурации')
    parser.add_argument('--test-dir', help='Папка с JSON-файлами результатов теста')
    parser.add_argument('--etalon-dir', help='Папка с эталонными JSON-файлами')
    parser.add_argument('--output-dir', help='Папка для сохранения результатов')
    parser.add_argument('--package', help='Фильтр по имени пакета (подстрока)')
    parser.add_argument('--log-level', help='Уровень логирования')
    parser.add_argument('--skip-diff', action='store_true', help='Пропустить этап сравнения (diff)')
    parser.add_argument('--skip-cause', action='store_true', help='Пропустить этап анализа причин')
    parser.add_argument('--skip-report', action='store_true', help='Пропустить этап построения сводного отчёта')
    args = parser.parse_args()

    config = load_config(args.config)
    app_cfg = config.get('app', {})
    stand_cfg = config.get('stand', {})
    cleaning_cfg = config.get('cleaning', {})
    masking_cfg = config.get('masking', {})
    llm_cfg = config.get('llm', {})
    cause_cfg = config.get('cause_analysis', {}).get('llm', {})
    report_cfg = config.get('report', {})

    log_level = args.log_level or app_cfg.get('log_level', 'INFO')
    test_dir = args.test_dir or stand_cfg.get('test_results_dir')
    etalon_dir = args.etalon_dir or stand_cfg.get('etalon_dir')
    output_dir = Path(args.output_dir or app_cfg.get('output_dir', './results'))

    if not test_dir or not etalon_dir:
        print("Не указаны директории тестов и эталонов. Проверьте конфиг или аргументы.")
        sys.exit(1)

    setup_logging(log_level)
    logging.info("=== Запуск анализатора регрессии ===")

    # Инициализация компонентов этапа 1 (diff)
    cleaner = LogCleaner(
        remove_fields=cleaning_cfg.get('remove_fields', []),
        kafka_keep_levels=cleaning_cfg.get('kafka_keep_levels', ['ERROR', 'WARNING']),
        clickhouse_keep_levels=cleaning_cfg.get('clickhouse_keep_levels', ['ERROR', 'WARNING'])
    )
    masker = DataMasker(
        enabled=masking_cfg.get('enabled', True),
        sensitive_fields=masking_cfg.get('sensitive_fields', []),
        keep_start=masking_cfg.get('keep_start', 2),
        keep_end=masking_cfg.get('keep_end', 2)
    )
    splitter = TaskSplitter(task_field='task_id')
    diff_llm = LLMComparatorClient(
        endpoint=llm_cfg['endpoint'],
        model=llm_cfg['model'],
        timeout=llm_cfg.get('timeout', 300),
        prompt_template=llm_cfg.get('prompt_template')
    )
    diff_builder = DiffBuilder()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Поиск пар файлов
    pairs = find_file_pairs(test_dir, etalon_dir, args.package)
    logging.info(f"Найдено пар для анализа: {len(pairs)}")
    if not pairs:
        logging.warning("Нет подходящих пар файлов. Завершение.")
        return

    diff_files: List[Path] = []
    # Этап 1: Diff
    if not args.skip_diff:
        logging.info("=== ЭТАП 1: Сравнение (diff) ===")
        for name, t_file, e_file in pairs:
            diff_path = process_test(name, t_file, e_file,
                                     cleaner, masker, splitter,
                                     diff_llm, diff_builder, output_dir)
            if diff_path:
                diff_files.append(diff_path)
        logging.info(f"Создано diff-файлов: {len(diff_files)}")
    else:
        # Если diff пропущен, ищем существующие diff-файлы в output_dir по именам тестов
        for name, _, _ in pairs:
            candidate = output_dir / f"log_{name}_diff.json"
            if candidate.exists():
                diff_files.append(candidate)
        logging.info(f"Найдено готовых diff-файлов: {len(diff_files)}")

    # Этап 2: Анализ причин
    cause_files: List[Path] = []
    if not args.skip_cause:
        if not diff_files:
            logging.error("Нет diff-файлов, этап анализа причин невозможен.")
        else:
            if not cause_cfg:
                logging.error("Не настроена LLM для анализа причин (cause_analysis.llm)")
            else:
                logging.info("=== ЭТАП 2: Анализ причин ===")
                cause_analyzer = LLMCauseAnalyzer(
                    endpoint=cause_cfg['endpoint'],
                    model=cause_cfg['model'],
                    timeout=cause_cfg.get('timeout', 300),
                    prompt_template=cause_cfg.get('prompt_template')
                )
                for diff_file in diff_files:
                    try:
                        cause_result = cause_analyzer.analyze(diff_file)
                        test_name = cause_result.get('test_name', diff_file.stem)
                        cause_path = output_dir / f"log_{test_name}_cause.json"
                        with open(cause_path, 'w', encoding='utf-8') as f:
                            json.dump(cause_result, f, ensure_ascii=False, indent=2)
                        cause_files.append(cause_path)
                        logging.info(f"Причины сохранены: {cause_path}")
                    except Exception as e:
                        logging.error(f"Не удалось проанализировать причины для {diff_file}: {e}")
    else:
        # Ищем существующие cause-файлы
        for diff_file in diff_files:
            test_name = diff_file.stem.replace('_diff', '')
            candidate = output_dir / f"log_{test_name}_cause.json"
            if candidate.exists():
                cause_files.append(candidate)
        logging.info(f"Найдено готовых файлов с причинами: {len(cause_files)}")

    # Этап 3: Сводный отчёт
    if not args.skip_report:
        if not cause_files:
            logging.warning("Нет файлов с причинами, этап отчёта пропущен.")
        else:
            logging.info("=== ЭТАП 3: Построение сводного отчёта ===")
            report_llm_cfg = report_cfg.get('llm', {})
            send_to_llm = report_cfg.get('send_to_llm', True)
            report_builder = ReportBuilder(
                endpoint=report_llm_cfg.get('endpoint') if send_to_llm else None,
                model=report_llm_cfg.get('model') if send_to_llm else None,
                timeout=report_llm_cfg.get('timeout', 300),
                prompt_template=report_llm_cfg.get('prompt_template'),
                send_to_llm=send_to_llm
            )
            report_output = output_dir / "regression_report.json"
            try:
                final = report_builder.build(cause_files, report_output)
                logging.info(f"Итоговый отчёт: {report_output}")
            except Exception as e:
                logging.error(f"Ошибка при создании отчёта: {e}")

    logging.info("=== Работа анализатора завершена ===")

if __name__ == '__main__':
    main()