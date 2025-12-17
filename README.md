# FreshFlats — Telegram‑бот для аренды квартир в Москве

Бот присылает новые объявления с Avito по вашим фильтрам (цена, количество комнат) прямо в Telegram.

## Возможности

- Мониторинг новых объявлений с Avito
- Фильтр по цене и количеству комнат
- Уведомления в личные сообщения Telegram
- Хранение объявлений в PostgreSQL

## Требования

- Python 3.10+
- PostgreSQL
- Chromium/Chrome (для парсера на Playwright)
- Telegram Bot Token от @BotFather

## Установка

1. git clone https://github.com/yourusername/freshflats.git
2. cd freshflats
3. python -m venv venv
4. source venv/bin/activate # или venv\Scripts\activate на Windows
5. pip install -r requirements.txt
6. playwright install chromium

Создайте `.env` по образцу `.env.example` и заполните:

* TELEGRAM_TOKEN=ваш_токен
* DB_URL=postgres://user:pass@localhost:5432/freshflats
* AVITO_URL=https://www.avito.ru/moskva/kvartiry/sdam/na_dlitelnyy_srok-ASgBAgICAkSSA8gQ8AeQUg
* PARSE_INTERVAL=300

## Запуск

В одном терминале:

    python parser.py

В другом:

    python bot.py

## Использование

1. В Telegram отправьте боту `/start`
2. Настройте цену и количество комнат через кнопки
3. Запустите поиск — бот будет присылать новые подходящие объявления

## Структура проекта

* freshflats/
* ├── bot.py # Telegram бот
* ├── parser.py # Парсер Avito
* ├── db.py # Работа с БД
* ├── test.py # Тесты
* ├── requirements.txt # Зависимости
* ├── .env # Конфигурация
* └── README.md # Документация

## Тестирование

pytest -v

## Использованные материалы

- [Aiogram документация](https://docs.aiogram.dev/) — библиотека для Telegram ботов
- [Playwright документация](https://playwright.dev/python/) — браузерная автоматизация
- [BeautifulSoup документация](https://www.crummy.com/software/BeautifulSoup/) — парсинг HTML