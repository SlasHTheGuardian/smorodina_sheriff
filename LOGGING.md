# Диагностика sheriff-bot

Бот пишет JSON в stdout; Docker сохраняет его в журнал контейнера. Дамп стека
при блокировке Python или аварии процесса пишется обычным текстом в stderr.
Файловые логи внутри контейнера не нужны; корневая файловая система остаётся read-only.

## Применение на сервере

Из папки проекта после доставки изменений:

```sh
docker compose up -d --build --no-deps bot
docker compose logs -f --tail=200 bot
docker compose ps
```

Это пересоздаёт только сервис бота. В репозитории уже настроена ротация Docker:
до трёх файлов по 10 MB. При активном использовании сохраняйте логи инцидента
до перезапуска/пересоздания контейнера, например:

```sh
docker compose logs --no-color --since=2h bot > sheriff-incident.log
docker compose exec -T bot python healthcheck.py
```

`LOG_LEVEL=INFO` по умолчанию: запуск, остановка, обработчики, операции БД,
запросы к Telegram и рейтингу, ошибки и heartbeat. Для подробностей временно
установите `LOG_LEVEL=DEBUG` в `.env` и пересоздайте сервис той же командой.
DEBUG добавляет каждый запрос polling и время каждого SQL-запроса.
Обычный long polling не считается медленным запросом.

Токен Telegram, DATABASE_URL, значения переменных с TOKEN/PASSWORD/SECRET и
пароли в URL маскируются, в том числе в traceback. Не записываются тела
Telegram updates, тексты сообщений, callback data, user_data, аргументы функций
и SQL-параметры. В логах остаются числовые user_id/chat_id для сопоставления событий.
Сообщения сторонних исключений могут содержать данные ошибки; учитывайте это
при передаче диагностического файла. DEBUG сторонних HTTP/Telegram/SQL-библиотек
отключён даже при LOG_LEVEL=DEBUG, чтобы не выводить payload и SQL-параметры.

## Как читать журнал

Общие поля: `timestamp` (UTC), `level`, `event`, `logger`, `pid`, `run_id`.
Для пользовательского запроса добавляются `update_id`, `user_id`, `chat_id`,
`handler`. Все вложенные обращения к Telegram, рейтингу и БД наследуют контекст.
Операции имеют `operation_id`, `operation`, `duration_ms`; начало без завершения
помогает найти зависший участок. Возвращаемые состояния диалогов — `handler.state`.
`operation.completed` означает завершение вызова; бизнес-отказ или перехваченная
ошибка отдельно отражаются в соответствующих событиях. Ошибки содержат цепочку
исключений и traceback.

| Событие / поле | Значение |
| --- | --- |
| `process.boot`, `process.starting` | Процесс начал загрузку; ещё не подтверждение готовности |
| `startup.ready_for_polling` | БД и меню команд готовы |
| `bot.started`, `polling.connected` | Обработчик запущен; получен первый успешный ответ getUpdates |
| `telegram.error`, category `network` | Сетевая ошибка с полным стеком, включая причину httpx |
| category `polling_conflict_check_other_instances_or_webhook` | Telegram вернул Conflict; проверьте второй экземпляр и webhook |
| `polling.recovered`, `bot.recovered` | Связь / состояние восстановились |
| `telegram.invalid_poll_response` | HTTP 200 с некорректным содержимым; такой ответ не обновляет здоровье polling |
| `db.query.failed`, `db.connection.invalidated` | Ошибка SQL или потеря соединения |
| `operation.completed` уровня WARNING | Операция заняла ≥ 5 с; SQL предупреждает уже от 500 мс |
| `notification.*.failed` | Не доставлено уведомление; есть ID получателя и встречи |
| `background_task.failed`, `asyncio.uncaught`, `thread.uncaught` | Сбой фоновой задачи или потока |
| `process.signal`, `bot.stopping`, `shutdown.completed`, `process.exited` | Причина и этапы остановки |
| `process.failed`, `process.uncaught` | Фатальная ошибка, процесс завершается ненулевым кодом |

## Контейнер работает, бот не отвечает

Каждые 30 секунд `bot.heartbeat` содержит возраст последнего успешного polling,
число его ошибок, длину очереди, счётчики обработанных updates/ошибок диспетчера,
активные операции с их возрастом, число asyncio-задач и задержку event loop.
Отсутствие пользовательских сообщений само по себе не считается проблемой.

Причины нездорового состояния:

- `polling_not_connected` — ещё нет успешного getUpdates; в первые 120 с это
  информационное событие ожидания подключения.
- `polling_stalled` — более 120 с без успешного ответа Telegram.
- `operation_stalled` — операция выполняется более 120 с.
- `update_queue_stalled` — очередь непуста, но новые updates не начинают обрабатываться более 120 с.
- `background_task_stopped` — завершился один из основных циклов PTB.
- `application_not_running` / `polling_not_running` — остановлено приложение / получение обновлений.

При изменении причины сбоя записываются расположения стеков asyncio-задач.
При блокировке event loop независимый таймер faulthandler выводит стеки потоков
через 120 с и повторяет дамп, пока event loop не оживёт. Таймер работает и при
зависании запуска. На Linux можно запросить дамп вручную, не останавливая бота:

```sh
docker compose exec -T bot python -c "import json,os,signal; from healthcheck import health_path; os.kill(json.loads(health_path().read_text())['pid'], signal.SIGUSR1)"
```

Healthcheck читает атомарно обновляемый `/tmp/sheriff-bot-health.json`, проверяет
состояние и свежесть heartbeat (до 90 с). Он не обращается к Telegram и не
забирает updates. После трёх неудачных проверок Docker пометит контейнер
`unhealthy`. `restart: unless-stopped` перезапускает завершившийся процесс;
сам статус `unhealthy` Docker Compose автоматически не перезапускает.
Монитор только диагностирует, не отменяет обработчики и не повторяет платежные
или регистрационные действия.

SIGKILL/OOM не дают Python записать финальную ошибку. Если журнал оборвался,
смотрите состояние контейнера на хосте:

```sh
docker inspect --format '{{json .State}}' "$(docker compose ps -aq bot)"
```

Проверьте `OOMKilled`, `ExitCode`, время завершения и результаты Healthcheck.

## Проверки

```sh
python -m unittest discover -s tests -p test_observability.py -v
python -m unittest discover -s tests -q
```

Тесты используют подменённый Telegram transport, httpx MockTransport и SQLite
в памяти. Производственные токены, Telegram и серверная БД не используются.
Расширения сверены с [Application PTB 21.6](https://docs.python-telegram-bot.org/en/v21.6/telegram.ext.application.html)
и [HTTPXRequest PTB 21.6](https://docs.python-telegram-bot.org/en/v21.6/telegram.request.httpxrequest.html).
Наблюдение основных фоновых задач опирается на имена задач закреплённой версии
21.6; при обновлении PTB проверьте соответствующий тест жизненного цикла.
