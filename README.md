# Footballistika (PostgreSQL)

Телеграм-бот + WebApp для збору футбольних прогнозів. Дані зберігаються у PostgreSQL через SQLAlchemy, міграції — Alembic.

## Вимоги
- Python 3.10+
- PostgreSQL (локально: `make db_up` із Docker Compose)
- Перемінні середовища:
  - `TELEGRAM_BOT_TOKEN`
  - `ADMIN_IDS` (через кому)
  - `DATABASE_URL` (та/або `DATABASE_POOL_URL` для pgbouncer)
  - `WEBAPP_URL` (опційно, лінк на WebApp)

## Швидкий старт (локально)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# підняти Postgres у Docker
make db_up

# застосувати міграції
alembic upgrade head

# імпорт із попередніх txt (ідемпотентно)
python tools/import_from_txt.py

# оновити матеріалізовану в'юху лідерборду
python tools/refresh_leaderboard.py

# запустити бота
python bot.py
```

Докер БД: `docker-compose.yml` створює користувача/БД `football/football` на порту 5432.  
Команди Makefile: `make db_up`, `make db_down`, `make db_logs`, `make db_backup`, `make refresh_leaderboard`.

## Міграції
- Конфіг: `alembic.ini`, метадані з `storage.py`.
- Стартова міграція: `migrations/versions/0001_initial.py` створює таблиці `matches`, `users`, `predictions`, `points_rules` та materialized view `leaderboard`.
- Рефреш лідерборду: `tools/refresh_leaderboard.py` викликає `REFRESH MATERIALIZED VIEW leaderboard`.

## Схема даних
- `matches`: `id` (bigserial), `team1`, `team2`, `score1`, `score2`, `status` (`scheduled|live|finished`), `started_at`, `updated_at`.  
  Статус `pending` з файлів мапиться на `scheduled`. Для `finished` рахунок обов'язковий.
- `users`: `id` (Telegram user_id), `username`, `created_at`.
- `predictions`: PK (`user_id`, `match_id`), рахунок, `created_at`. Індекси: `user_id`, `match_id`.
- `points_rules`: конфіг балів. Дефолт `exact=5`, `result=1`. Можна правити значення без змін коду.
- `leaderboard` (materialized view): обчислює бали за finished матчі на основі правил (точний рахунок — exact, правильний результат/різниця — result).

## CLI
- `python tools/import_from_txt.py` — ідемпотентний імпорт `data/matches.txt` та `data/predictions.txt` у БД (для міграції зі старих файлів).
- `python tools/refresh_leaderboard.py` — рефреш матеріалізованої в'юхи.

## Бот
- Адмінка: додавання матчу (`scheduled`), введення результату (`finished`), середні/всі прогнози, точність.
- Користувач: зробити прогноз (до 17:59 за Києвом, один на матч), перегляд таблиці/точностей.
- Логіка нарахування: точний рахунок — 5, правильний результат — 1 (налаштовується в `points_rules`).

## WebApp API
- `/api/webapp/profile` — профіль та статистика користувача.
- `/api/webapp/matches` — матчі без прогнозу користувача + прапор дедлайну.
- `/api/webapp/prediction` — збереження прогнозу (перевірка дедлайну/дублікату).
- `/api/webapp/leaderboard`, `/api/webapp/result-accuracy`, `/api/webapp/goal-accuracy` — топ-10 + рядок користувача.
Усі ендпоінти вимагають валідний `initData` від Telegram WebApp.

## Деплой (Railway/Vercel)
- Додай `DATABASE_URL`/`DATABASE_POOL_URL` у змінні середовища сервісів Railway (бот/API) та Vercel (WebApp).
- Після деплою застосуй міграції: `alembic upgrade head`.
- Міграція даних: одноразово запусти `python tools/import_from_txt.py` (якщо є історичні txt).
- Регулярно (або після оновлень результатів) викликай `python tools/refresh_leaderboard.py` або роби це в коді за потреби.

## Нотатки
- У продакшні файли `data/*.txt` не використовуються, лише як джерело для імпорту.
- При статусі `finished` не міняємо назви команд (перевірка в коді).
- Для дедлайну прогнозів використовується час Києва 17:59. Бекенд блокує збереження після цього часу.
