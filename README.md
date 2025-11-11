# 🤖 Telegram Bot: Оживление фото за 100₽

## 🔧 Технологии
- Telegram Bot API
- Replicate (анимация фото)
- ЮKassa (платежи)
- PostgreSQL (хранение данных)
- FastAPI (вебхуки + админка)
- Render (хостинг)
- GitHub (CI/CD)

## 🚀 Как запустить

1. **Создай бота в Telegram** через @BotFather → получи `BOT_TOKEN`
2. **Зарегистрируйся на** [Replicate](https://replicate.com) → получи `REPLICATE_API_TOKEN`
3. **Подключи ЮKassa** → получи `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY`
4. **Создай репозиторий на GitHub** и загрузи все файлы
5. **Зарегистрируйся на Render** → импортируй репозиторий → выбери `render.yaml`
6. **Добавь переменные окружения** в Render (в разделе *Environment*)
7. **Настрой вебхуки ЮKassa** — URL: `https://your-render-app.onrender.com/webhook`
8. **Нажми Deploy** — бот запустится!

## 📊 Админ-панель

- URL: `https://your-render-app.onrender.com/admin`
- Логин/пароль: задаются в переменных окружения
- Показывает:
  - Количество пользователей
  - Успешные платежи
  - Доход
  - Последние сессии

## 💡 Советы
- Используй модель: `cjwbw/animatediff` — лучшая для анимации лиц.
- Проверяй модель на Replicate: https://replicate.com/cjwbw/animatediff
- Вебхуки ЮKassa работают мгновенно — без polling.
- PostgreSQL хранит данные между перезапусками.

## 📞 Поддержка
Если что-то не работает — пиши в Issues!