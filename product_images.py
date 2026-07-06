"""Сопоставление товаров каталога с картинками.

Картинки грузятся отдельным Excel-файлом через админку.
Формат файла: ищем колонку с названием товара и колонку со ссылкой (URL)
на картинку. Матч с каталогом — по нормализованному названию (raw_name).
"""
import logging
import re
from typing import Any, Optional

import openpyxl

log = logging.getLogger(__name__)


def norm_key(name: str) -> str:
    """Нормализованный ключ названия для точного матча:
    lower + схлопывание пробелов + strip."""
    if not name:
        return ""
    s = str(name).replace("\xa0", " ").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


# Заголовки, по которым определяем колонку названия и колонку ссылки.
_NAME_HEADERS = ("товар", "наименован", "название", "name")
_URL_HEADERS = ("ссылк", "url")  # приоритетные
_URL_HEADERS_FALLBACK = ("фото", "картин", "image", "изображ")  # запасные


def _looks_like_url(v: Any) -> bool:
    return isinstance(v, str) and v.strip().lower().startswith(("http://", "https://"))


def _find_columns(rows: list[tuple]) -> Optional[tuple[int, int, int]]:
    """Находит (header_idx, name_col, url_col). None если не найдено."""
    for idx, row in enumerate(rows[:15]):
        if not row:
            continue
        name_col = url_col = url_fallback = None
        for ci, cell in enumerate(row):
            if not isinstance(cell, str):
                continue
            low = cell.strip().lower()
            if name_col is None and any(h in low for h in _NAME_HEADERS):
                name_col = ci
            if url_col is None and any(h in low for h in _URL_HEADERS):
                url_col = ci
            if url_fallback is None and any(h in low for h in _URL_HEADERS_FALLBACK):
                url_fallback = ci
        chosen_url = url_col if url_col is not None else url_fallback
        if name_col is not None and chosen_url is not None:
            return idx, name_col, chosen_url
    return None


def parse_images_xlsx(path: str) -> tuple[list[tuple[str, str]], dict]:
    """Читает файл, возвращает (pairs, stats).
    pairs = [(norm_key(name), image_url), ...] только валидные URL.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    stats = {"sheets_tried": [], "rows": 0, "matched_cols": None,
             "with_url": 0, "no_url": 0, "no_name": 0}
    best: list[tuple[str, str]] = []

    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        found = _find_columns(rows)
        if not found:
            # эвристика: колонка названия=перв. текстовая, ссылка=любая с http
            found = _fallback_columns(rows)
        if not found:
            stats["sheets_tried"].append(f"{ws.title}: колонки не найдены")
            continue
        header_idx, name_col, url_col = found
        pairs: list[tuple[str, str]] = []
        for row in rows[header_idx + 1:]:
            if not row:
                continue
            name = row[name_col] if name_col < len(row) else None
            url = row[url_col] if url_col < len(row) else None
            if not name or not isinstance(name, str) or not name.strip():
                stats["no_name"] += 1
                continue
            if not _looks_like_url(url):
                stats["no_url"] += 1
                continue
            pairs.append((norm_key(name), url.strip()))
        stats["sheets_tried"].append(
            f"{ws.title}: cols name={name_col} url={url_col} pairs={len(pairs)}"
        )
        if len(pairs) > len(best):
            best = pairs
            stats["matched_cols"] = (ws.title, name_col, url_col)
    wb.close()
    stats["with_url"] = len(best)
    stats["rows"] = len(best)
    # dedup по ключу (последнее значение побеждает)
    dedup = dict(best)
    return list(dedup.items()), stats


def _fallback_columns(rows: list[tuple]) -> Optional[tuple[int, int, int]]:
    """Если заголовки не распознаны: ищем строку данных, где есть http-ячейка,
    берём её как url_col, а первую длинную текстовую (не http) — как name_col."""
    for idx, row in enumerate(rows[:30]):
        if not row:
            continue
        url_col = None
        for ci, cell in enumerate(row):
            if _looks_like_url(cell):
                url_col = ci
                break
        if url_col is None:
            continue
        name_col = None
        for ci, cell in enumerate(row):
            if ci == url_col:
                continue
            if isinstance(cell, str) and len(cell.strip()) >= 5 and not _looks_like_url(cell):
                name_col = ci
                break
        if name_col is not None:
            return max(0, idx - 1), name_col, url_col
    return None
