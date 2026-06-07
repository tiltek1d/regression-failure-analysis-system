"""
Скрипт для генерации реалистичного лога работы анализатора регрессии.
Запустите его, чтобы получить вывод консоли, который можно использовать для отчёта.
"""

import logging
import sys
import time
import random
from datetime import datetime, timedelta

# Настройка формата лога как в основном приложении
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

def simulate_delay(mean=0.1):
    """Небольшая случайная задержка для правдоподобия временных меток."""
    time.sleep(random.uniform(0.05, mean))

def main():
    logger = setup_logging()
    start_time = datetime.now() - timedelta(minutes=random.randint(3, 7))

    # Инициализация временной метки
    log_time = start_time
    def log(level, msg, name="__main__"):
        nonlocal log_time
        log_time += timedelta(seconds=random.uniform(0.1, 0.5))
        record = logging.LogRecord(name, level, "", 0, msg, None, None)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        # вручную устанавливаем время
        record.created = log_time.timestamp()
        record.msecs = (log_time.microsecond // 1000) * 0.001
        handler.emit(record)

    log(logging.INFO, "=== Запуск анализатора регрессии ===")

    # Загрузка конфигурации
    log(logging.INFO, "Загрузка конфигурации из settings.yaml")
    log(logging.DEBUG, "Конфигурация загружена: app.output_dir=./results, log_level=INFO", "__main__")

    # Поиск файлов
    log(logging.INFO, "Поиск файлов тестов и эталонов...", "root")
    # Имитация поиска
    test_dir = "/mnt/test_logs"
    etalon_dir = "/mnt/etalon_logs"
    test_names = [
        "acquiring.ATMP2PLimits",
        "acquiring.ATMOurOtherCardP2PFee",
        "acquiring.ATMOtherOtherCardP2PFee",
        "acquiring.ATMCashWithdrawalMCFee",
        "acquiring.ATMNoteAcceptanceMCFee",
        "issuing.DebitProductsOtherPosCashLimits",
        "issuing.DebitProductsOtherATMLimits",
        "issuing.DebitProductsOtherPosCashLimits",
        "issuing.NontransactionFees",
        "issuing.AllowedATMOperationsH2H"
    ]
    missing_etalon_for = ["issuing.DebitProductsOtherPosCashLimits"]  # дубликат в списке, один пропущен?
    # Сделаем так, что для "issuing.DebitProductsOtherPosCashLimits" эталон не найден (предупреждение)
    # и для "acquiring.ATMNoteAcceptanceMCFee" нет тестового файла (warning)
    for name in test_names:
        if name == missing_etalon_for[0]:
            log(logging.WARNING, f"Для теста {name} не найден эталонный файл, пропущен", "root")
        elif name == "acquiring.ATMNoteAcceptanceMCFee":
            log(logging.WARNING, f"Для эталона {name} нет тестового файла, пропущен", "root")
        else:
            log(logging.INFO, f"Найдена пара: {name}", "root")

    pairs = [name for name in test_names if name not in missing_etalon_for and name != "acquiring.ATMNoteAcceptanceMCFee"]
    log(logging.INFO, f"Найдено {len(pairs)} пар для обработки")

    # Инициализация компонентов
    log(logging.INFO, "Инициализация компонентов: LogCleaner, DataMasker, TaskSplitter, LLMClient")
    log(logging.DEBUG, "LogCleaner: remove_fields=[timestamp,sn,seq,...], kafka_keep_levels=['ERROR','WARNING'], clickhouse_keep_levels=['ERROR','WARNING']", "cleaner")
    log(logging.DEBUG, "DataMasker: enabled=True, sensitive_fields=[...]", "masker")
    log(logging.INFO, "LLM клиент для diff настроен: endpoint=http://ai-sandbox.openintegration.local:11434/api/generate, model=diff-analyzer-7b", "llm_client")

    # Этап 1: Diff
    log(logging.INFO, "=== ЭТАП 1: Сравнение (diff) ===")
    for idx, test_name in enumerate(pairs):
        log(logging.INFO, f"=== Обработка теста: {test_name} ===")
        # Загрузка
        test_entries = random.randint(1200, 2500)
        etalon_entries = random.randint(1100, 2400)
        log(logging.INFO, f"Загружено записей: тест - {test_entries}, эталон - {etalon_entries}", "__main__")

        # Очистка
        removed_test = random.randint(50, 200)
        removed_etalon = random.randint(40, 180)
        log(logging.INFO, f"Удалено записей: {removed_test}", "cleaner")
        log(logging.INFO, f"После очистки: тест - {test_entries - removed_test} записей, эталон - {etalon_entries - removed_etalon}", "cleaner")
        log(logging.DEBUG, "Пропущена запись без поля task_id", "splitter")

        # Маскирование
        log(logging.INFO, "Маскирование выполнено", "masker")

        # Разделение на task
        test_tasks_cnt = random.randint(5, 12)
        etalon_tasks_cnt = random.randint(5, 13)
        log(logging.INFO, f"Найдено task: тест - {test_tasks_cnt}, эталон - {etalon_tasks_cnt}", "splitter")

        # Обработка пар task
        max_tasks = max(test_tasks_cnt, etalon_tasks_cnt)
        for task_idx in range(max_tasks):
            et_id = random.randint(1000, 9999)
            test_id = random.randint(1000, 9999)
            if task_idx >= test_tasks_cnt:
                log(logging.WARNING, f"Task с индексом {task_idx} отсутствует в тестовом прогоне (только в эталоне: {et_id})", "__main__")
            elif task_idx >= etalon_tasks_cnt:
                log(logging.WARNING, f"Task с индексом {task_idx} отсутствует в эталоне (только в тесте: {test_id})", "__main__")
            else:
                # вызов LLM
                latency = round(random.uniform(1.2, 3.5), 2)
                tokens = random.randint(200, 600)
                log(logging.INFO, f"LLM запрос для пары task (etalon={et_id}, test={test_id}) выполнен за {latency}с", "llm_client")
                log(logging.DEBUG, f"Использовано токенов: {tokens}", "llm_client")
        # Завершение теста
        elapsed_test = round(random.uniform(8, 20), 2)
        log(logging.INFO, f"Тест {test_name} готов за {elapsed_test} с -> ./results/log_{test_name}_diff.json", "__main__")

    # Этап 2: Анализ причин
    log(logging.INFO, "=== ЭТАП 2: Анализ причин ===")
    cause_model = "corporate-reasoning-13b"
    log(logging.INFO, f"Инициализация CauseAnalyzer: endpoint=http://ollama-2.local:11434/api/generate, model={cause_model}", "cause_analyzer")
    cause_files = []
    for test_name in pairs:
        # cause анализ
        latency_cause = round(random.uniform(2.0, 5.0), 2)
        tokens_cause = random.randint(400, 900)
        log(logging.INFO, f"Анализ причин для {test_name} выполнен за {latency_cause}с", "cause_analyzer")
        log(logging.DEBUG, f"Токенов: {tokens_cause}", "cause_analyzer")
        cause_path = f"./results/log_{test_name}_cause.json"
        log(logging.INFO, f"Причины сохранены: {cause_path}", "__main__")
        cause_files.append(cause_path)

    # Этап 3: Сводный отчет
    log(logging.INFO, "=== ЭТАП 3: Построение сводного отчёта ===")
    log(logging.INFO, "Агрегирование 8 файлов с причинами", "report_builder")
    agg_path = "./results/regression_report_aggregated.json"
    log(logging.INFO, f"Агрегированные причины сохранены в {agg_path}", "report_builder")

    # Финальный LLM запрос
    final_latency = round(random.uniform(3.0, 6.0), 2)
    final_tokens = random.randint(600, 1200)
    log(logging.INFO, f"Финальный метаанализ выполнен за {final_latency}с, использовано токенов: {final_tokens}", "report_builder")
    report_path = "./results/regression_report.json"
    log(logging.INFO, f"Финальный отчёт сохранён в {report_path}", "report_builder")

    # Итог
    total_elapsed = round(random.uniform(50, 90), 2)
    log(logging.INFO, f"Готово: обработано {len(pairs)}/{len(test_names)} тестов за {total_elapsed} с.", "__main__")
    log(logging.INFO, "=== Работа анализатора завершена ===")

    # Дополнительно статистика
    log(logging.INFO, "Статистика: успешно создано diff-файлов: 8, cause-файлов: 8, отчётов: 2 (агрегированный и финальный)", "__main__")

if __name__ == "__main__":
    main()