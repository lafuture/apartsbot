import asyncio
import re
import os
from dataclasses import dataclass
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from db import init_db, add_apart

load_dotenv()

# Получаем URL из переменных окружения или параметров командной строки
AVITO_URL = os.getenv("AVITO_URL",
                      "https://www.avito.ru/moskva/kvartiry/sdam/na_dlitelnyy_srok-ASgBAgICAkSSA8gQ8AeQUg?cd=1")
PARSE_INTERVAL = int(os.getenv("PARSE_INTERVAL", "300"))


def in_digits(s: str) -> bool:
    """
    Проверяет, что строка состоит только из цифр.

    :param s: Входная строка для проверки.
    :type s: str
    :returns: True, если все символы строки являются цифрами, иначе False.
    :rtype: bool
    """
    try:
        return all(ch.isdigit() for ch in s)
    except (TypeError, AttributeError) as e:
        raise ValueError(f"Некорректный тип данных для проверки цифр: {e}")


def refactor_time_to_metro(time_to_metro: str) -> int:
    """
    Извлекает числовые значения из строки с временем до метро
    и возвращает максимальное найденное значение.
    Строка может содержать текст и диапазоны, функция находит все целые
    числа и выбирает среди них наибольшее.

    :param time_to_metro: Строка с описанием времени до метро,
        например ``"10–15 минут пешком"``.
    :type time_to_metro: str
    :returns: Максимальное найденное целое число, либо 0, если чисел нет.
    :rtype: int
    """
    try:
        s = time_to_metro.replace("–", " ").split()
        res = 0
        for t in s:
            if in_digits(t):
                tdigit = int(t)
                if tdigit > res:
                    res = tdigit
        return res
    except Exception as e:
        print(f"[refactor_time_to_metro] Ошибка обработки '{time_to_metro}': {e}")
        return 0


def split_add(add: str) -> tuple[int, int]:
    """
    Разбирает строку с дополнительными условиями (залог, комиссия)
    и возвращает их числовые значения.
    Поддерживаются фразы вида «без залога», «залог 30 000», «без комиссии»,
    «комиссия 50%»; из текста извлекаются числа для залога и комиссии.

    :param add: Строка с дополнительными условиями, разделёнными « · ».
    :type add: str
    :returns: Кортеж (размер залога в рублях, размер комиссии в рублях).
    :rtype: tuple[int, int]
    """
    try:
        parts = add.split(" · ")
        deposit = 0
        comission = 0

        for p in parts:
            p = p.strip().replace("\u00A0", " ")
            pl = p.lower()

            if "без залога" in pl:
                deposit = 0
            elif "залог" in pl:
                m = re.search(r"(\d[\d\s]*)", p)
                if m:
                    num = m.group(1).replace(" ", "")
                    try:
                        deposit = int(num)
                    except ValueError:
                        pass

            if "без комиссии" in pl:
                comission = 0
            elif "комис" in pl:
                m = re.search(r"(\d[\d\s]*)", p)
                if m:
                    num = m.group(1).replace(" ", "")
                    try:
                        comission = int(num)
                    except ValueError:
                        pass

        return deposit, comission
    except Exception as e:
        print(f"[split_add] Ошибка обработки '{add}': {e}")
        return 0, 0


def split_title(title: str) -> tuple[int, float, int, int]:
    """
    Разбирает заголовок объявления и извлекает количество комнат,
    площадь, этаж квартиры и этажность дома.
    Поддерживает указание площади в квадратных метрах, форматы с «студия»,
    а также этажность в виде ``"этаж/этажность"``.

    :param title: Заголовок объявления Avito, содержащий параметры квартиры.
    :type title: str
    :returns: Кортеж (кол-во комнат, площадь в м², этаж, этажность дома).
    :rtype: tuple[int, float, int, int]
    """
    try:
        title = title.replace("эт.", "").replace("этаж", "").replace("\u00A0", " ")
        squares = 0.0
        rooms = 0
        apart_floor = 0
        house_floor = 0

        # Площадь
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*м²", title)
        if m:
            s = m.group(1).replace(",", ".")
            try:
                squares = float(s)
            except ValueError:
                pass

        # Комнаты
        if "студ" in title.lower():
            rooms = 0
        else:
            m = re.search(r"(\d+)[-\s]*к", title)
            if m:
                try:
                    rooms = int(m.group(1))
                except ValueError:
                    pass

        # Этажи
        m = re.search(r"(\d+)\s*\/\s*(\d+)", title)
        if m:
            try:
                apart_floor = int(m.group(1))
                house_floor = int(m.group(2))
            except ValueError:
                pass

        return rooms, squares, apart_floor, house_floor
    except Exception as e:
        print(f"[split_title] Ошибка обработки '{title}': {e}")
        return 0, 0.0, 0, 0


@dataclass
class Ad:
    """
    Представляет одно объявление о сдаче квартиры с основными параметрами.

    :ivar id: Уникальный идентификатор объявления на Avito.
    :type id: int
    :ivar title: Заголовок объявления.
    :type title: str
    :ivar link: Полная ссылка на страницу объявления.
    :type link: str
    :ivar price: Стоимость аренды в месяц в рублях.
    :type price: int
    :ivar comission: Размер комиссии в рублях.
    :type comission: int
    :ivar squares: Площадь квартиры в квадратных метрах.
    :type squares: float
    :ivar apart_floor: Этаж квартиры.
    :type apart_floor: int
    :ivar house_floor: Общее количество этажей в доме.
    :type house_floor: int
    :ivar rooms: Количество комнат (0 = студия).
    :type rooms: int
    :ivar deposit: Размер залога в рублях.
    :type deposit: int
    :ivar metro: Название ближайшей станции метро, если указано.
    :type metro: str
    :ivar time_to_metro: Время до метро в минутах, если указано.
    :type time_to_metro: int
    """
    id: int
    title: str
    link: str
    price: int
    comission: int
    squares: float
    apart_floor: int
    house_floor: int
    rooms: int
    deposit: int
    metro: str
    time_to_metro: int


async def fetch_html() -> str:
    """
    Загружает HTML страницы выдачи Avito с помощью Playwright.
    Открывает браузер Chromium, переходит по AVITO_URL, ждёт загрузку и
    возможное прохождение капчи, скроллит страницу вниз и возвращает HTML.

    :returns: HTML-код страницы выдачи с объявлениями.
    :rtype: str
    :raises RuntimeError: При ошибках загрузки страницы.
    """
    try:
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=False)
            except Exception as e:
                raise RuntimeError(f"Не удалось запустить браузер: {e}")

            try:
                page = await browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                        "Version/18.3.1 Safari/605.1.15"
                    )
                )

                print("[playwright] открываю", AVITO_URL)
                await page.goto(AVITO_URL, timeout=120_000)

                print("[playwright] жду 2 секунды для загрузки / капчи")
                await page.wait_for_timeout(20_00)

                try:
                    await page.wait_for_selector("div[data-marker='item']", timeout=30_000)
                    print("[playwright] найден селектор item")
                except Exception as e:
                    print("[playwright] не дождался item:", e)

                await page.evaluate("window.scrollBy(0, document.body.scrollHeight);")
                await page.wait_for_timeout(2_000)

                html = await page.content()
                print("[playwright] длина html:", len(html))

                return html

            except Exception as e:
                raise RuntimeError(f"Ошибка при загрузке страницы: {e}")
            finally:
                await browser.close()

    except Exception as e:
        raise RuntimeError(f"Критическая ошибка fetch_html: {e}")


def parse_and_save(html: str):
    """
    Разбирает HTML страницы Avito, извлекает объявления и сохраняет их в БД.
    Для каждого блока ``div[data-marker='item']`` формирует объект Ad,
    берёт нужные поля и вызывает add_apart для сохранения в таблицу aparts.

    :param html: HTML-код страницы выдачи Avito.
    :type html: str
    :raises ValueError: При ошибках парсинга HTML.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("div[data-marker='item']")
        print("[parse] items:", len(items))

        if not items:
            raise ValueError("Не найдено ни одного объявления на странице")

        added = 0

        for g in items:
            try:
                id_attr = g.get("data-item-id", "")
                try:
                    int_id = int(id_attr)
                except (ValueError, TypeError):
                    continue

                title_el = g.select_one("a[data-marker='item-title']")
                title = title_el.get_text(strip=True) if title_el else ""

                rooms, squares, apart_floor, house_floor = split_title(title)

                price_meta = g.select_one("p[data-marker='item-price'] meta[itemprop='price']")
                price_str = price_meta.get("content", "") if price_meta else "0"
                try:
                    price = int(price_str)
                except (ValueError, TypeError):
                    price = 0

                add_el = g.select_one("p[data-marker='item-specific-params']")
                add_text = add_el.get_text(strip=True) if add_el else ""
                deposit, comission = split_add(add_text)

                metro = ""
                time_to_metro = 0
                loc_p = g.select("div[data-marker='item-location'] p")
                if len(loc_p) > 1:
                    spans = loc_p[1].find_all("span")
                    if len(spans) > 1:
                        metro = spans[1].get_text(strip=True)
                    if len(spans) > 2:
                        time_to_metro = refactor_time_to_metro(
                            spans[2].get_text(strip=True)
                        )

                link_el = g.find("a")
                link = link_el.get("href", "") if link_el else ""
                if link and not link.startswith("http"):
                    link = urljoin("https://www.avito.ru", link)

                ad = Ad(
                    id=int_id,
                    title=title,
                    link=link,
                    price=price,
                    comission=comission,
                    squares=squares,
                    apart_floor=apart_floor,
                    house_floor=house_floor,
                    rooms=rooms,
                    deposit=deposit,
                    metro=metro,
                    time_to_metro=time_to_metro,
                )

                try:
                    add_apart({
                        "id": ad.id,
                        "title": ad.title,
                        "link": ad.link,
                        "price": ad.price,
                        "rooms": ad.rooms,
                    })
                    print(f"✓ added {ad.id} - {ad.title}")
                    added += 1
                except Exception as e:
                    print(f"[parse] add_apart error {ad.id}: {e}")

            except Exception as e:
                print(f"[parse] ошибка обработки объявления: {e}")
                continue

        print("[parse] total added:", added)

    except Exception as e:
        raise ValueError(f"Критическая ошибка parse_and_save: {e}")


async def parse_loop():
    """
    Бесконечный цикл парсинга с интервалом PARSE_INTERVAL секунд.

    :raises RuntimeError: При критических ошибках парсинга.
    """
    print(f"[parser] Запуск парсера с интервалом {PARSE_INTERVAL} секунд")

    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        try:
            print(f"[parser] Начало парсинга")
            html = await fetch_html()
            parse_and_save(html)
            print(f"[parser] Парсинг завершён. Следующий запуск через {PARSE_INTERVAL} секунд")
            consecutive_errors = 0

        except Exception as e:
            consecutive_errors += 1
            print(f"[parser] Ошибка при парсинге ({consecutive_errors}/{max_consecutive_errors}): {e}")

            if consecutive_errors >= max_consecutive_errors:
                raise RuntimeError(
                    f"Превышено максимальное количество последовательных ошибок ({max_consecutive_errors}). "
                    "Парсер остановлен."
                )

            print(f"[parser] Повтор через {PARSE_INTERVAL} секунд")

        await asyncio.sleep(PARSE_INTERVAL)


async def main():
    """
    Точка входа: инициализирует базу данных и запускает бесконечный цикл парсинга.

    :raises RuntimeError: При критических ошибках инициализации.
    """
    try:
        print("[parser] Инициализация базы данных...")
        init_db()
        print("[parser] База данных инициализирована успешно")

        await parse_loop()

    except Exception as e:
        print(f"[parser] Критическая ошибка: {e}")
        raise RuntimeError(f"Не удалось запустить парсер: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[parser] Парсер остановлен пользователем")
    except Exception as e:
        print(f"\n[parser] Фатальная ошибка: {e}")
        exit(1)
