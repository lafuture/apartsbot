import os
from datetime import datetime, timedelta

import pg8000.native as pg
from dotenv import load_dotenv


load_dotenv()

DB_URL = os.getenv("DB_URL")


def _parse_db_url(url: str):
    """
    Разбирает строку подключения к PostgreSQL в формате postgres:// и
    возвращает словарь параметров для подключения.

    Ожидается URL вида:
    postgres://user:password@host:port/dbname?params...

    :param url: Строка подключения к базе данных.
    :type url: str
    :returns: Словарь с ключами user, password, host, port, database.
    :rtype: dict[str, object]
    :raises AssertionError: Если строка не начинается с 'postgres://'.
    """
    assert url.startswith("postgres://")
    url = url[len("postgres://"):]
    auth, rest = url.split("@", 1)
    user, password = auth.split(":", 1)

    hostport, db_and_params = rest.split("/", 1)
    if "?" in db_and_params:
        dbname, _params = db_and_params.split("?", 1)
    else:
        dbname = db_and_params

    if ":" in hostport:
        host, port = hostport.split(":", 1)
        port = int(port)
    else:
        host, port = hostport, 5432

    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "database": dbname,
    }


def get_conn():
    """
    Создаёт и возвращает новое соединение с базой данных PostgreSQL.

    Строка подключения берётся из переменной окружения DB_URL и
    разбирается функцией _parse_db_url.

    :returns: Открытое соединение с базой данных.
    :rtype: pg.Connection
    :raises RuntimeError: Если переменная окружения DB_URL не задана.
    """
    if not DB_URL:
        raise RuntimeError("DB_URL не задан в переменных окружения")
    params = _parse_db_url(DB_URL)
    return pg.Connection(
        user=params["user"],
        password=params["password"],
        host=params["host"],
        port=params["port"],
        database=params["database"],
    )


def init_db():
    """
    Инициализирует структуру базы данных, создавая таблицу aparts,
    если она ещё не существует.

    Таблица aparts хранит объявления с полями:
    id, title, link, price, rooms, created_at.
    """
    conn = get_conn()
    try:
        conn.run("""
            CREATE TABLE IF NOT EXISTS aparts (
                id BIGINT PRIMARY KEY,
                title TEXT NOT NULL,
                link TEXT NOT NULL,
                price INTEGER NOT NULL,
                rooms INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)
    finally:
        conn.close()


def add_apart(apart: dict):
    """
    Добавляет новое объявление в таблицу aparts.

    Если объявление с таким id уже существует, вставка игнорируется
    за счёт ON CONFLICT (id) DO NOTHING.

    :param apart: Словарь с данными объявления
        (ожидаются ключи id, title, link, price, rooms).
    :type apart: dict
    """
    conn = get_conn()
    try:
        conn.run(
            """
            INSERT INTO aparts (id, title, link, price, rooms)
            VALUES (:id, :title, :link, :price, :rooms)
            ON CONFLICT (id) DO NOTHING;
            """,
            id=apart["id"],
            title=apart["title"],
            link=apart["link"],
            price=apart["price"],
            rooms=apart["rooms"],
        )
    finally:
        conn.close()

def get_new_aparts(
    min_price: int | None,
    max_price: int | None,
    rooms: list[int] | None,
    since: datetime,
    limit: int = 20,
):
    """
    Возвращает новые объявления, созданные после указанного момента,
    с учётом фильтров по цене и количеству комнат.

    Используется для периодической выборки свежих объявлений,
    отсортированных по дате создания по возрастанию.

    :param min_price: Минимальная цена, либо None для отсутствия нижней границы.
    :type min_price: int | None
    :param max_price: Максимальная цена, либо None для отсутствия верхней границы.
    :type max_price: int | None
    :param rooms: Список допустимого количества комнат (0 = студия),
        либо None для отсутствия фильтра.
    :type rooms: list[int] | None
    :param since: Время, после которого считаются объявления новыми.
    :type since: datetime
    :param limit: Максимальное количество возвращаемых объявлений.
    :type limit: int
    :returns: Список словарей с полями id, title, link, price, rooms, created_at.
    :rtype: list[dict]
    """
    conn = get_conn()
    try:
        query = """
            SELECT id, title, link, price, rooms, created_at
            FROM aparts
            WHERE created_at > :since
        """
        params: dict[str, object] = {"since": since}

        if min_price is not None:
            query += " AND price >= :min_price"
            params["min_price"] = min_price

        if max_price is not None:
            query += " AND price <= :max_price"
            params["max_price"] = max_price

        if rooms:
            placeholders = []
            for idx, r in enumerate(rooms):
                name = f"room_{idx}"
                placeholders.append(f":{name}")
                params[name] = r
            query += f" AND rooms IN ({', '.join(placeholders)})"

        query += " ORDER BY created_at ASC LIMIT :limit"
        params["limit"] = limit

        rows = conn.run(query, **params)
        cols = [c["name"] for c in conn.columns]
        result = [dict(zip(cols, row)) for row in rows]
        return result
    finally:
        conn.close()
