"""Нормализация категорий каталога: переименование, объединение,
порядок, эмодзи, очистка названий товаров.
"""
from __future__ import annotations
import re

# Маппинг исходного значения "Тип" из прайса -> финальный ключ категории
RAW_TO_KEY = {
    "набор": "ustroystva",
    "одноразовая эсдн": "odnorazki",
    "одноразов": "odnorazki",          # на всякий случай
    "картридж": "kartridzhi",
    "картриджи": "kartridzhi",
    "испаритель": "kartridzhi",
    "испарители": "kartridzhi",
    "жидкость": "zhidkost",
    "ароматизатор": "aromatizator",
    "глицерин": "glicerin",
    "кальянная смесь": "tabak_kalyan",
    "нагреваемый табак": "tabak_kalyan",
    "уголь": "ugol",
    "нюхательный табак": "nyuh_tabak",
    "жевательный табак": "zhev_tabak",
    "энерджетик": "energetiki",
    "энерджетики": "energetiki",
    "энергетик": "energetiki",
    "энергетики": "energetiki",
}

# Финальные категории: ключ -> (эмодзи + название, порядок, столбец)
# col=1 — левый столбец, col=2 — правый
CATEGORY_META = {
    "odnorazki":     {"title": "💨 Одноразки",            "order": 1,  "col": 1},
    "ustroystva":    {"title": "🔋 Устройства",     "order": 2,  "col": 1},
    "kartridzhi":    {"title": "🧩 Картриджи", "order": 3,  "col": 1},
    "zhidkost":      {"title": "💧 Жидкость",             "order": 4,  "col": 1},
    "aromatizator":  {"title": "🌸 Ароматизатор",         "order": 5,  "col": 1},
    "glicerin":      {"title": "🧪 Глицерин",             "order": 6,  "col": 1},
    "tabak_kalyan":  {"title": "🌿 Табак кальянный",    "order": 7,  "col": 2},
    "ugol":          {"title": "🔥 Уголь",                "order": 8,  "col": 2},
    "nyuh_tabak":    {"title": "👃 Нюхательный табак",    "order": 9,  "col": 2},
    "zhev_tabak":    {"title": "👅 Жевательный табак",    "order": 10, "col": 2},
    "energetiki":    {"title": "⚡️ Энерджетики",          "order": 11, "col": 2},
    "kofe":          {"title": "☕️ Кофе",                 "order": 12, "col": 1},
    "raznoe":        {"title": "🎒 Разное",               "order": 99, "col": 2},
}


# Категории БЕЗ возрастного ограничения (доступны без верификации 18+).
FREE_CATEGORIES = frozenset({"kofe", "energetiki", "glicerin", "aromatizator", "raznoe"})


def is_age_restricted(key: str) -> bool:
    """True — если категория требует подтверждения возраста 18+."""
    return key not in FREE_CATEGORIES


def normalize_category(raw: str) -> str:
    """Привести исходный 'Тип' к финальному ключу категории."""
    if not raw:
        return "raznoe"
    n = raw.strip().lower()
    # точное совпадение
    if n in RAW_TO_KEY:
        return RAW_TO_KEY[n]
    # частичное (по началу слова)
    for needle, key in RAW_TO_KEY.items():
        if n.startswith(needle) or needle in n:
            return key
    # эвристика по ключевым словам (любой порядок слов)
    if "жеват" in n:
        return "zhev_tabak"
    if "нюхат" in n or "нюх" in n:
        return "nyuh_tabak"
    if "кальян" in n:
        return "tabak_kalyan"
    if "энерд" in n or "энерг" in n:
        return "energetiki"
    if any(w in n for w in ("кофе","американо","латте","эспрессо","эспресо","капучино","капуччино","раф","мокко","мокачино","флэт","флет")):
        return "kofe"
    if "уголь" in n or "угли" in n:
        return "ugol"
    return "raznoe"


def category_title(key: str) -> str:
    meta = CATEGORY_META.get(key)
    return meta["title"] if meta else key


def sorted_category_keys(present: set[str]) -> list[str]:
    """Отсортировать присутствующие категории в нужном порядке."""
    keys = [k for k in present if k in CATEGORY_META]
    keys.sort(key=lambda k: CATEGORY_META[k]["order"])
    # неизвестные ключи в конец
    extra = sorted(k for k in present if k not in CATEGORY_META)
    return keys + extra


# Слова категорий, которые нужно вырезать из НАЗВАНИЯ товара (п.7)
_CLEAN_PREFIXES = [
    "одноразовая эсдн", "одноразовая", "одноразка", "одноразки",
    "набор", "картриджи", "картридж", "испарители", "испаритель",
    "жидкость", "ароматизатор", "глицерин",
    "кальянная смесь", "нагреваемый табак",
    "табак для кальяна", "табак жевательный", "табак нюхательный",
    "уголь", "нюхательный табак", "жевательный табак",
    "энерджетик", "энергетик", "энерджетики", "энергетики",
]


def clean_name(name: str) -> str:
    """Убрать из названия слово-категорию (п.7) и хвост с количеством (п.8)."""
    if not name:
        return name
    s = name.strip()
    low = s.lower()
    # убрать ведущее слово категории
    for pref in _CLEAN_PREFIXES:
        if low.startswith(pref):
            s = s[len(pref):].lstrip(" -–—:,.")
            break
    # убрать хвост вида "10 шт", "x10", "(60 мл)" с количеством штук
    s = re.sub(r"[\s,;]*\b\d+\s*шт\.?\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[\s,;]*[xх]\s*\d+\b", "", s, flags=re.IGNORECASE)
    s = s.strip(" -–—:,.")
    return s or name.strip()



# Многословные бренды: если название начинается с любого из них (без учёта регистра),
# производитель берётся целиком. Порядок — от длинных к коротким.
MULTI_WORD_BRANDS = [
    "VAN ERKOMS",
]


def _match_multiword_brand(s: str):
    low = s.lower()
    for brand in MULTI_WORD_BRANDS:
        if low.startswith(brand.lower()):
            return brand
    return None


def extract_manufacturer(name: str) -> str:
    """Грубо определить производителя как первое слово/бренд названия (п.6).

    Берём первое 'слово' до пробела/запятки/дефиса. Если оно короткое
    служебное — берём первые два.
    """
    s = name.strip()
    mb = _match_multiword_brand(s)
    if mb:
        return mb
    m = re.match(r"^([\"«]?[A-Za-zА-Яа-я0-9\-&\.]+)", s)
    if not m:
        return "Прочее"
    word = m.group(1).strip("\"«»").strip()
    if len(word) <= 2 and " " in s:
        # добавим второе слово
        parts = s.split()
        if len(parts) >= 2:
            return f"{parts[0]} {parts[1]}".strip("\"«»")
    return word or "Прочее"


def category_rows(present: set) -> list:
    """Разложить категории по рядам. Длинные названия — на всю ширину,
    короткие группируются по 2 в ряд (в порядке 'order')."""
    keys = sorted_category_keys(present)
    LONG = 14  # порог длины title для отдельной строки
    rows = []
    buf = []
    for k in keys:
        title = CATEGORY_META.get(k, {}).get("title", k)
        if len(title) > LONG:
            if buf:
                rows.append(buf)
                buf = []
            rows.append([k])
        else:
            buf.append(k)
            if len(buf) == 2:
                rows.append(buf)
                buf = []
    if buf:
        rows.append(buf)
    return rows
