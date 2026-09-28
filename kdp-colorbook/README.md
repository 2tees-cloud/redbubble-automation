# KDP Coloring Books — ядро (AI-роутер)

Два роутера с автопереключением: **текст** (Gemini, Groq, Cerebras, Z.AI, Mistral, OpenRouter, xAI)
и **картинки** (Cloudflare FLUX → HuggingFace → Pollinations). Порядок в `config.yaml` = приоритет.

Если провайдер упал, он встаёт на паузу, а запрос уходит к следующему:
- 429 (лимит) → пауза по Retry-After или 1 мин, растёт ×2 при повторах (до 12 ч)
- 401/403 (плохой ключ) → 24 ч
- 5xx / таймаут → 30 с и растёт
- 200, но мусор (не JSON, не картинка, маленькая картинка) → тоже переход дальше

Паузы и расход за день хранятся в `data/router_state.db` и переживают перезапуск.

## Постобработка и PDF для KDP
Генератор выдаёт ~1024×1024 с серыми тенями и мусором, а KDP нужно 300 DPI (8.5×11" = 2550×3300 px).
Растягивать картинку бесполезно, поэтому страница векторизуется:
```
картинка → серый → порог (Otsu, тени светлее 200 уходят в белое) → удаление точек и дырок
        → potrace (кривые Безье) → PDF: линии чёткие при любом разрешении
```
Интерьер собирается собственным PDF-писателем: в файле нет шрифтов вообще (reportlab добавляет
невстроенный Helvetica, из-за чего KDP может отклонить файл). Поля у корешка берутся из таблицы KDP
по числу страниц, картинки идут только на правых страницах, обороты пустые, число страниц чётное.
Настройки — секции `postprocess` и `book` в `config.yaml`.

## Запуск
```bash
pip install -r requirements.txt
cp .env.example .env        # вписать ключи
python tests/test_fallback.py          # офлайн-тесты логики
python scripts/check_router.py --models  # какие модели доступны по вашим ключам
python scripts/check_router.py           # живой тест: JSON с темами + 1 страница раскраски в out/
python scripts/check_router.py --status  # кто на паузе, сколько запросов сегодня
python tests/test_postprocess.py         # офлайн-тесты постобработки и PDF
python scripts/build_interior.py out/pages --svg   # папка картинок → out/interior.pdf (+ чистые SVG)
```

## Использование в коде
```python
from core import load_routers
text, image = load_routers()
themes = text.chat_json("3 темы раскрасок для 4-8 лет, JSON")["data"]
page = image.generate("coloring page, cute dinosaur, thick black outlines, white background")
page["image"].save("page.png")

from core import book, postprocess
vec = postprocess.process(page["image"])            # чистый вектор
book.build_interior([vec, ...], "out/interior.pdf")  # PDF-интерьер для KDP
```
Добавить провайдера — новая запись в `config.yaml` + ключ в `.env`, код трогать не нужно.
