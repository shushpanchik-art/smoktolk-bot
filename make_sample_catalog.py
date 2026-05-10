"""Создаёт data/catalog.xlsx с примерным ассортиментом и подарками.
Запустить один раз: python make_sample_catalog.py
"""
import os
import openpyxl

os.makedirs("data", exist_ok=True)
wb = openpyxl.Workbook()

ws = wb.active
ws.title = "products"
ws.append(["sku", "name", "category", "price", "stock", "description"])
products = [
    ("LIQ-001", "Husky Mint Ice 30ml 20мг",        "liquid",      650, "в наличии", "Освежающая мята со льдом."),
    ("LIQ-002", "Jam Monster Strawberry 100ml",    "liquid",      1200,"в наличии", "Клубничный джем на тосте."),
    ("LIQ-003", "Bad Drip Don't Care Bear 60ml",   "liquid",      1100,"мало",      "Микс мармеладных мишек."),
    ("DEV-001", "Vaporesso XROS 4",                "device",      2900,"в наличии", "Pod-система, 1000 mAh."),
    ("DEV-002", "GeekVape Aegis Boost Pro 2",      "device",      4500,"в наличии", "Защищённая POD-MOD, 2100 mAh."),
    ("POD-001", "Картриджи XROS Mesh 0.6Ω (4 шт)", "pods",        750, "в наличии", "Сменные картриджи."),
    ("DIS-001", "Elf Bar 5000 Манго",              "disposable",  900, "в наличии", "Одноразка 5000 затяжек."),
    ("DIS-002", "HQD Cuvie Plus Виноград",         "disposable",  700, "в наличии", "Одноразка 1200 затяжек."),
    ("ACC-001", "Чехол силиконовый XROS 4",        "accessories", 350, "в наличии", "Защита от ударов и царапин."),
    ("ACC-002", "Шнурок-держатель",                "accessories", 250, "в наличии", "Чтобы не терять устройство."),
    ("CBL-001", "Кабель USB-C 1м усиленный",       "cables",      400, "в наличии", "Оплётка, до 3А."),
    ("TLS-001", "Пинцет керамический",             "tools",       300, "в наличии", "Для замены спиралей."),
    ("SWT-001", "Жвачка Mentos Mint",              "sweets",      80,  "в наличии", "Освежить дыхание."),
    ("SWT-002", "Леденцы Halls Extra Strong",      "sweets",      120, "в наличии", "Ментоловые леденцы."),
    ("TOB-001", "Heets Amber",                     "tobacco",     250, "в наличии", "Стики для IQOS."),
]
for p in products:
    ws.append(p)

ws2 = wb.create_sheet("gifts")
ws2.append(["code", "name", "min_level", "description"])
gifts = [
    ("GIFT-LIQ-10",  "Жидкость 10 мл (на выбор)", 3, "Любая жидкость объёмом 10 мл из акционного списка."),
    ("GIFT-COIL",    "Сменный испаритель",        3, "Один испаритель к вашему устройству."),
    ("GIFT-SWEETS",  "Сладкий комплимент",        3, "Жвачка или леденцы на выбор."),
    ("GIFT-CABLE",   "Кабель USB-C",              4, "Зарядный кабель усиленный."),
    ("GIFT-CASE",    "Силиконовый чехол",         4, "Чехол для популярных устройств."),
    ("GIFT-LIQ-30",  "Жидкость 30 мл",            5, "Любая жидкость 30 мл из акционного списка."),
    ("GIFT-PODS",    "Упаковка картриджей",       5, "Сменные картриджи."),
]
for g in gifts:
    ws2.append(g)

wb.save("data/catalog.xlsx")
print("✅ data/catalog.xlsx создан:", len(products), "товаров,", len(gifts), "подарков")
