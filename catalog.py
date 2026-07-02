"""Модуль работы с каталогом товаров (Excel).

Скачивает файл с Яндекс.Диска (если задан CATALOG_URL) и кэширует
список товаров в памяти. Используется ботом и handlers/catalog.py.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional
from urllib.parse import quote

import aiohttp
import openpyxl

import config
import catalog_norm

log = logging.getLogger(__name__)

# Путь к локальному файлу каталога
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CATALOG_FILE = os.path.join(DATA_DIR, "catalog.xlsx")

# Ожидаемые столбцы (в порядке заголовков первой строки)
REQUIRED_COLUMNS = ("sku", "name", "category", "price", "stock", "description")

# Кэш товаров в памяти
_products: list[dict[str, Any]] = []


async def _download_yadisk(public_url: str, dest: str) -> bool:
    """Скачать файл с публичной ссылки Яндекс.Диска."""
    api = (
        "https://cloud-api.yandex.net/v1/disk/public/resources/download"
        f"?public_key={quote(public_url, safe='')}"
    )
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(api) as r:
            if r.status != 200:
                log.error("Yandex API status %s: %s", r.status, await r.text())
                return False
            data = await r.json()
            href = data.get("href")
        if not href:
            log.error("Yandex API: no href in response")
            return False
        async with s.get(href) as r:
            if r.status != 200:
                log.error("Download status %s", r.status)
                return False
            content = await r.read()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(content)
    return True


async def _download_direct(url: str, dest: str) -> bool:
    """Скачать файл по прямой ссылке."""
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(url) as r:
            if r.status != 200:
                log.error("Download status %s for %s", r.status, url)
                return False
            content = await r.read()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(content)
    return True


async def _download(url: str, dest: str) -> bool:
    if "disk.yandex" in url or "yadi.sk" in url:
        return await _download_yadisk(url, dest)
    return await _download_direct(url, dest)


# Допустимые значения для атрибута border style в xlsx
_VALID_BORDER_STYLES = {
    "hair", "medium", "slantDashDot", "mediumDashDot", "mediumDashDotDot",
    "thin", "dotted", "dashDotDot", "dashDot", "mediumDashed", "dashed",
    "thick", "double", "none",
}


def _sanitize_styles_xml(xml_bytes: bytes) -> bytes:
    """Заменить невалидные значения border style на 'thin' (безопасный дефолт).

    Некоторые редакторы (LibreOffice, экспорт из веб-таблиц) пишут
    значения вроде style="" или style="continuous", из-за которых
    openpyxl падает с ValueError.
    """
    import re
    text = xml_bytes.decode("utf-8", errors="replace")
    fixed = 0

    def _repl(m: "re.Match[str]") -> str:
        nonlocal fixed
        val = m.group(1)
        if val in _VALID_BORDER_STYLES:
            return m.group(0)
        fixed += 1
        return m.group(0).replace(f'style="{val}"', 'style="thin"')

    # Все теги border-семейства имеют атрибут style="..."
    pattern = re.compile(r'\bstyle="([^"]*)"')
    text = pattern.sub(_repl, text)
    if fixed:
        log.warning("styles.xml: sanitized %d invalid border style value(s)", fixed)
    return text.encode("utf-8")


def _load_workbook_safe(path: str):
    """Открыть xlsx, при необходимости починив битый styles.xml."""
    try:
        return openpyxl.load_workbook(path, data_only=True)
    except ValueError as e:
        msg = str(e).lower()
        if "style" not in msg and "stylesheet" not in msg:
            raise
        log.warning("Catalog xlsx has invalid styles, attempting sanitization: %s", e)

    # Fallback: распакуем zip, починим styles.xml, перепакуем во временный файл
    import zipfile

    tmp_path = path + ".sanitized.xlsx"
    with zipfile.ZipFile(path, "r") as zin:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "xl/styles.xml":
                    data = _sanitize_styles_xml(data)
                zout.writestr(item, data)

    try:
        wb = openpyxl.load_workbook(tmp_path, data_only=True)
        log.info("Catalog xlsx loaded after sanitization")
        return wb
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _detect_category(name: str) -> str:
    """Определить категорию товара по названию (fallback)."""
    return catalog_norm.normalize_category(name)


def _find_header_row(rows: list) -> tuple[int, dict[str, int]]:
    """Найти строку с заголовками и вернуть её индекс и маппинг {имя_колонки: индекс}.

    Заголовки ищем по характерным словам: "Товары", "Цена продажи", "Количество".
    """
    targets = {
        "num": ("№",),  # символ №
        "name": ("товары",),
        "price": ("цена продажи",),
        "stock": ("количество",),
        "rec": ("рекомендация",),
        "category": ("тип",),
        "desc": ("описание",),
        "country": ("страна",),
        "marking": ("акциз", "маркировка"),
    }
    for row_idx, row in enumerate(rows):
        if not row:
            continue
        cells_lc = [
            (c.strip().lower() if isinstance(c, str) else "") for c in row
        ]
        # Достаточно, чтобы нашлись name и price — остальное опционально
        col_map: dict[str, int] = {}
        for key, needles in targets.items():
            for col_idx, cell in enumerate(cells_lc):
                if any(needle in cell for needle in needles):
                    col_map[key] = col_idx
                    break
        if "name" in col_map and "price" in col_map:
            return row_idx, col_map
    raise ValueError("Header row not found (need columns 'Товары' and 'Цена продажи')")


def _parse_xlsx(path: str) -> list[dict[str, Any]]:
    """Прочитать Excel и вернуть список товаров.

    Формат файла — печатная форма прайса (1С/Контур):
      • заголовки не в первой строке
      • колонки 'Артикул'/'sku' могут быть пустыми → генерируем SKU из №
      • категория не задана → определяем по названию
      • в конце файла служебные строки 'Средняя', 'Итого:', 'Менеджер'
    """
    wb = _load_workbook_safe(path)
    if "Ассортимент" in wb.sheetnames:
        ws = wb["Ассортимент"]
    else:
        ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        log.warning("Catalog: empty sheet")
        return []

    try:
        header_idx, col_map = _find_header_row(rows)
    except ValueError as e:
        log.error("Catalog: %s", e)
        return []

    log.info(
        "Catalog: header at row %d, columns: %s",
        header_idx + 1, col_map,
    )

    name_col = col_map["name"]
    price_col = col_map["price"]
    stock_col = col_map.get("stock")
    rec_col = col_map.get("rec")
    cat_col = col_map.get("category")
    desc_col = col_map.get("desc")
    country_col = col_map.get("country")
    marking_col = col_map.get("marking")

    result: list[dict[str, Any]] = []
    skipped_no_num = 0
    skipped_no_name = 0
    skipped_no_price = 0

    for row in rows[header_idx + 1:]:
        if not row or all(c is None for c in row):
            continue

        # Берём только строки, где в колонке № стоит целое число.
        # У служебных хвостов ('Средняя', 'Итого:') там либо None, либо текст.
        num_col = col_map.get("num", 0)
        num_cell = row[num_col] if num_col < len(row) else None
        try:
            num = int(num_cell)
        except (TypeError, ValueError):
            skipped_no_num += 1
            continue

        name = row[name_col] if name_col < len(row) else None
        if not name or not isinstance(name, str) or not name.strip():
            skipped_no_name += 1
            continue
        name = name.strip()

        price_raw = row[price_col] if price_col < len(row) else None
        try:
            price = int(round(float(price_raw)))
        except (TypeError, ValueError):
            skipped_no_price += 1
            continue
        if price <= 0:
            skipped_no_price += 1
            continue

        # Stock
        stock_val = row[stock_col] if stock_col is not None and stock_col < len(row) else None
        if isinstance(stock_val, (int, float)):
            stock = str(int(stock_val))
        elif isinstance(stock_val, str) and stock_val.strip():
            stock = stock_val.strip()
        else:
            stock = "уточняйте"

        # Description ← колонка "Описание" (иначе "Рекомендация")
        def _cell(idx):
            return row[idx] if idx is not None and idx < len(row) else None
        desc_val = _cell(desc_col)
        rec_val = _cell(rec_col)
        base = desc_val if isinstance(desc_val, str) and desc_val.strip() else rec_val
        description = base.strip() if isinstance(base, str) else ""
        country_val = _cell(country_col)
        if isinstance(country_val, str) and country_val.strip():
            description += f"\nСтрана: {country_val.strip()}"
        marking_val = _cell(marking_col)
        marking = marking_val.strip() if isinstance(marking_val, str) else ""

        raw_cat = (
            row[cat_col].strip()
            if cat_col is not None and cat_col < len(row)
            and isinstance(row[cat_col], str) and row[cat_col].strip()
            else ""
        )
        cat_key = catalog_norm.normalize_category(raw_cat) if raw_cat else _detect_category(name)
        item = {
            "sku": f"SKU-{num:04d}",
            "name": catalog_norm.clean_name(name),
            "raw_name": name,
            "category": cat_key,
            "manufacturer": catalog_norm.extract_manufacturer(catalog_norm.clean_name(name)),
            "price": price,
            "stock": stock,
            "marking": marking,
            "description": description,
        }
        result.append(item)

    log.info(
        "Catalog: parsed %d products (skipped: no_num=%d, no_name=%d, no_price=%d)",
        len(result), skipped_no_num, skipped_no_name, skipped_no_price,
    )
    return result


async def refresh(force: bool = False) -> int:
    """Обновить каталог. Возвращает кол-во товаров."""
    global _products
    url = getattr(config, "CATALOG_URL", "") or ""

    need_download = force or not os.path.exists(CATALOG_FILE)
    if need_download and url:
        log.info("Downloading catalog from %s", url)
        ok = await _download(url, CATALOG_FILE)
        if not ok:
            log.warning("Catalog download failed, using existing file if any")

    if not os.path.exists(CATALOG_FILE):
        log.warning("Catalog file not found: %s", CATALOG_FILE)
        _products = []
        return 0

    try:
        _products = _parse_xlsx(CATALOG_FILE)
        log.info("Catalog loaded: %d products", len(_products))
    except Exception as e:
        log.exception("Catalog parse error: %s", e)
        _products = []
    return len(_products)


async def get_products() -> list[dict[str, Any]]:
    if not _products:
        await refresh(force=False)
    return list(_products)


async def get_product(sku: str) -> Optional[dict[str, Any]]:
    if not _products:
        await refresh(force=False)
    for p in _products:
        if p["sku"] == sku:
            return p
    return None


# ===== ПОДАРКИ (заглушка: список из конфига) =====
_GIFTS = [
    {"code": "GIFT_KEYRING",  "name": "Брелок SMOKTOLK",       "min_level": 3, "description": "Фирменный брелок за 1 ₽."},
    {"code": "GIFT_STICKER",  "name": "Набор стикеров",         "min_level": 3, "description": "Виниловые стикеры с логотипом."},
    {"code": "GIFT_CABLE",    "name": "USB-C кабель 1 м",       "min_level": 4, "description": "Качественный кабель для зарядки пода."},
    {"code": "GIFT_LANYARD",  "name": "Шнурок для пода",        "min_level": 4, "description": "Удобный силиконовый шнурок."},
    {"code": "GIFT_TSHIRT",   "name": "Футболка SMOKTOLK",      "min_level": 5, "description": "Хлопок 100%, размер уточняется при выдаче."},
    {"code": "GIFT_HOODIE",   "name": "Худи SMOKTOLK",          "min_level": 6, "description": "Премиум-мерч для VIP-уровня."},
]


async def get_gifts() -> list[dict]:
    return list(_GIFTS)


async def get_gift(code: str):
    for g in _GIFTS:
        if g["code"] == code:
            return g
    return None
