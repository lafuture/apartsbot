
# test.py
import pytest
from bot import UserState, get_state, main_keyboard, stop_keyboard, user_states
from db import _parse_db_url
from parser import in_digits, refactor_time_to_metro, split_add, split_title, Ad


@pytest.fixture(autouse=True)
def clear_states():
    """Очищаем состояния перед каждым тестом"""
    user_states.clear()
    yield
    user_states.clear()

# UserState
def test_user_state_positive():
    """Положительный: создание с параметрами"""
    state = UserState(min_price=30000, max_price=60000, rooms=[1, 2])
    assert state.min_price == 30000
    assert state.max_price == 60000
    assert state.rooms == [1, 2]


def test_user_state_negative():
    """Отрицательный: дефолтные значения (нет данных)"""
    state = UserState()
    assert state.min_price is None
    assert state.rooms is None
    assert state.searching is False


# get_state
def test_get_state_positive():
    """Положительный: получение существующего состояния"""
    state1 = get_state(100)
    state1.min_price = 50000
    state2 = get_state(100)
    assert state2.min_price == 50000
    assert state1 is state2


def test_get_state_negative():
    """Отрицательный: создание нового состояния (не существовало)"""
    state = get_state(999)
    assert isinstance(state, UserState)
    assert state.min_price is None


# main_keyboard
def test_main_keyboard_positive():
    """Положительный: клавиатура с фильтрами"""
    state = UserState(min_price=30000, max_price=60000, rooms=[0, 1, 2])
    kb = main_keyboard(state)
    text_price = kb.inline_keyboard[0][0].text
    text_rooms = kb.inline_keyboard[1][0].text
    assert "от 30000" in text_price
    assert "до 60000" in text_price
    assert "студия" in text_rooms
    assert "1" in text_rooms


def test_main_keyboard_negative():
    """Отрицательный: клавиатура без фильтров"""
    state = UserState()
    kb = main_keyboard(state)
    assert "Установить цену" in kb.inline_keyboard[0][0].text
    assert "Установить комнаты" in kb.inline_keyboard[1][0].text


# stop_keyboard
def test_stop_keyboard_positive():
    """Положительный: корректная структура"""
    kb = stop_keyboard()
    assert len(kb.inline_keyboard) == 1
    assert "Остановить поиск" in kb.inline_keyboard[0][0].text
    assert kb.inline_keyboard[0][0].callback_data == "stop_search"


def test_stop_keyboard_negative():
    """Отрицательный: проверка что нет других кнопок"""
    kb = stop_keyboard()
    assert len(kb.inline_keyboard) != 0
    assert len(kb.inline_keyboard[0]) == 1

# _parse_db_url
def test_parse_db_url_positive():
    """Положительный: корректный URL"""
    url = "postgres://user:pass@localhost:5432/mydb"
    result = _parse_db_url(url)
    assert result["user"] == "user"
    assert result["password"] == "pass"
    assert result["host"] == "localhost"
    assert result["port"] == 5432
    assert result["database"] == "mydb"

def test_parse_db_url_negative():
    """Отрицательный: неверный префикс"""
    with pytest.raises(AssertionError):
        _parse_db_url("mysql://user:pass@host/db")

# in_digits
def test_in_digits_positive():
    """Положительный: строка из цифр"""
    assert in_digits("12345") is True
    assert in_digits("0") is True


def test_in_digits_negative():
    """Отрицательный: строка с нецифровыми символами"""
    assert in_digits("123abc") is False
    assert in_digits("12 34") is False


# refactor_time_to_metro
def test_refactor_time_to_metro_positive():
    """Положительный: извлечение максимального числа"""
    assert refactor_time_to_metro("10–15 минут") == 15
    assert refactor_time_to_metro("5 мин") == 5


def test_refactor_time_to_metro_negative():
    """Отрицательный: нет чисел в строке"""
    assert refactor_time_to_metro("пешком") == 0
    assert refactor_time_to_metro("") == 0


# split_add
def test_split_add_positive():
    """Положительный: парсинг залога и комиссии"""
    assert split_add("залог 30 000 · комиссия 15 000") == (30000, 15000)
    assert split_add("залог 50000") == (50000, 0)


def test_split_add_negative():
    """Отрицательный: нет данных или некорректный текст"""
    assert split_add("") == (0, 0)
    assert split_add("какой-то текст") == (0, 0)


# split_title
def test_split_title_positive():
    """Положительный: полный парсинг заголовка"""
    assert split_title("2-к квартира, 60 м², 7/12 эт.") == (2, 60.0, 7, 12)
    assert split_title("Студия, 25 м², 5/10 эт.") == (0, 25.0, 5, 10)


def test_split_title_negative():
    """Отрицательный: пустой или неполный заголовок"""
    assert split_title("") == (0, 0.0, 0, 0)
    assert split_title("квартира") == (0, 0.0, 0, 0)


# Ad
def test_ad_positive():
    """Положительный: создание объявления с данными"""
    ad = Ad(
        id=123, title="Test", link="http://test.com",
        price=50000, comission=5000, squares=45.5,
        apart_floor=5, house_floor=10, rooms=2,
        deposit=30000, metro="Сокольники", time_to_metro=10
    )
    assert ad.id == 123
    assert ad.price == 50000
    assert ad.rooms == 2


def test_ad_negative():
    """Отрицательный: создание с пустыми/нулевыми значениями"""
    ad = Ad(
        id=0, title="", link="",
        price=0, comission=0, squares=0.0,
        apart_floor=0, house_floor=0, rooms=0,
        deposit=0, metro="", time_to_metro=0
    )
    assert ad.id == 0
    assert ad.price == 0
    assert ad.rooms == 0
