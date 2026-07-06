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
    if not name:
        return ""
    s = str(name).replace("\xa0", " ").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


_NAME_HEADERS = ("товар", "наименован", "название", "name")
_URL_HEADERS = ("ссылк", "url", "фото", "картин", "image", "изображ")


def _looks_like_url(v: Any) -> bool:
    return isinstance(v, str) and v.strip().lower().startswith(("http://", "https://"))


def _count_urls_in_col(rows: list[tuple], header_idx: int, col: int) -> int:
    """Сколько http-значений в колонке col в строках данных."""
    cnt = 0
    for row in rows[header_idx + 1:]:
        if not row or col >= len(row):
            continue
        if _looks_like_url(row[col]):
            cnt += 1
    return cnt


def _find_columns(rows: list[tuple]) -> Optional[tuple[int, int, int]]:
    """Находит (header_idx, name_col, url_col).

    URL-колонку выбираем по ФАКТИЧЕСКОМУ содержимому: среди всех колонок,
    чей заголовок похож на url/фото/ссылку, берём ту, где больше http-значений.
    Если ни в одной такой колонке нет URL — сканируем все колонки.
    """
    for idx, row in enumerate(rows[:15]):
        if not row:
            continue
        name_col = None
        url_candidates: list[int] = []
        for ci, cell in enumerate(row):
            if not isinstance(cell, str):
                continue
            low = cell.strip().lower()
            if name_col is None and any(h in low for h in _NAME_HEADERS):
                name_col = ci
            if any(h in low for h in _URL_HEADERS):
                url_candidates.append(ci)
        if name_col is None:
            continue

        # выбираем url-колонку по реальному наличию http в данных
        best_url = None
        best_cnt = 0
        for ci in url_candidates:
            c = _count_urls_in_col(rows, idx, ci)
            if c > best_cnt:
                best_cnt = c
                best_url = ci
        # если по заголовкам не нашли данных — сканируем ВСЕ колонки
        if best_url is None:
            ncols = max(len(r) for r in rows[idx + 1:idx + 30] if r) if len(rows) > idx + 1 else 0
            for ci in range(ncols):
                if ci == name_col:
                    continue
                c = _count_urls_in_col(rows, idx, ci)
                if c > best_cnt:
                    best_cnt = c
                    best_url = ci

        if best_url is not None and best_cnt > 0:
            return idx, name_col, best_url
    return None


def parse_images_xlsx(path: str) -> tuple[list[tuple[str, str]], dict]:
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
    dedup = dict(best)
    return list(dedup.items()), stats


def _fallback_columns(rows: list[tuple]) -> Optional[tuple[int, int, int]]:
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
