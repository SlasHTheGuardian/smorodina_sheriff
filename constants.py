# Главное меню
CB_LEARN    = "learn"          # раздел "Обучение"
CB_RULES    = "rules"          # раздел "Правила игры"
CB_GAMES    = "games"          # раздел "Запись на игры"
CB_STATS    = "my_stats"       # личный рейтинг и статистика
CB_MY_RATING = "my_rating"     # рейтинг из внешнего сервиса
CB_MY_RESULTS = "my_results"   # завершённые партии пользователя
CB_CREATE_GAME_NICKNAME = "create_game_nickname"
CB_CANCEL_GAME_NICKNAME = "cancel_game_nickname"
CB_ADMIN_RESULTS = "admin_results"  # ввод результатов (только админы)
CB_ADMIN_CREATE_EVENT = "admin_create_event"
CB_ADMIN_EVENTS = "admin_events"
CB_ADMIN_EVENT_VIEW_PREFIX = "admin_event_view:"
CB_ADMIN_EVENT_EDIT_PREFIX = "admin_event_edit:"
CB_ADMIN_EVENT_EDIT_FIELD_PREFIX = "admin_event_edit_field:"
CB_ADMIN_EVENT_EDIT_CLEAR = "admin_event_edit_clear"
CB_ADMIN_EVENT_DELETE_PREFIX = "admin_event_delete:"
CB_ADMIN_EVENT_DELETE_CONFIRM_PREFIX = "admin_event_delete_ok:"
CB_ADMIN_EVENT_SKIP_LOCATION = "admin_event_skip_location"
CB_ADMIN_EVENT_SKIP_NOTE = "admin_event_skip_note"
CB_ADMIN_EVENT_CONFIRM = "admin_event_confirm"
CB_ADMIN_EVENT_CANCEL = "admin_event_cancel"
CB_MAIN     = "main_menu"      # возврат в главное меню

# Запись на игры
CB_MY_GAMES         = "my_games"   # мои записи
CB_GAME_PREFIX      = "game:"      # game:<id>    — карточка игры
CB_GAME_REG_PREFIX  = "greg:"      # greg:<id>    — записаться
CB_GAME_PAID_PREFIX = "gpaid:"     # gpaid:<id>   — подтвердить отправку оплаты
CB_GAME_CANCEL_PREFIX = "gcancel:" # gcancel:<id> — отменить запись
CB_GAME_CANCEL_CONFIRM_PREFIX = "gcancelok:"  # gcancelok:<id> — подтвердить отмену

# Разделы правил
CB_RULE_PREFIX = "rule:"       # rule:<section_key> — показать контент
CB_RSUB_PREFIX = "rsub:"       # rsub:<name>        — открыть подменю

# Подменю обучения → баланс и противовес
CB_BALANCE      = "balance"         # подменю "Баланс и противовес"
CB_BALANCE_FOR  = "balance_for"     # "Игра в баланс"
CB_BALANCE_AGST = "balance_against" # "Игра в противовес"

# Подменю обучения → распил стола
CB_SAWING        = "sawing"          # кнопка "Пилим стол"
CB_SAWING_PLAY   = "sawing_play"     # начать / повторить мини-игру
CB_SAWING_ANS_YES = "sawing_ans_yes" # ответ "Да"
CB_SAWING_ANS_NO  = "sawing_ans_no"  # ответ "Нет"
CB_THEORY   = "sawing_theory"  # "Нет, давай начнем с теории"
CB_PRACTICE = "sawing_practice"# "Да, хочу попрактиковаться!"
CB_NEXT_1   = "sawing_next_1"  # Далее после 1-го блока теории
CB_NEXT_2   = "sawing_next_2"  # Далее после 2-го блока теории
CB_SKIP     = "sawing_skip"    # "Не сейчас" → подменю обучения
CB_TRY      = "sawing_try"     # "Да, давай!" → практика

# Квиз «Фолы и наказания»
CB_QUIZ            = "quiz"        # вход в квиз из меню обучения
CB_QUIZ_START      = "quiz_start"  # начать / перезапустить квиз
CB_QUIZ_NEXT       = "quiz_next"   # следующий вопрос
CB_QUIZ_FINISH     = "quiz_finish" # завершить и показать итог
CB_QUIZ_ANS_PREFIX = "quiz_ans:"   # quiz_ans:<category> — выбранный ответ

# Мини-игра «Ночной детектив»
CB_DETECTIVE         = "detective" # вход из меню обучения
CB_DET_NEW_PREFIX    = "det_new:"  # det_new:<difficulty> — новая партия (easy|hard)
CB_DET_CHECK         = "det_check" # проверить выбор
CB_DET_TOGGLE_PREFIX = "det_t:"    # det_t:<n> — отметить/снять игрока №n
