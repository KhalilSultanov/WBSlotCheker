# config.py

import os

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7370767857:AAHv1NF8IpOdP1BQEBT6gl8EgN40aPae-JA")

# Wildberries API Key
WILDBERRIES_API_KEY = os.getenv("WILDBERRIES_API_KEY","eyJhbGciOiJFUzI1NiIsImtpZCI6IjIwMjQwOTA0djEiLCJ0eXAiOiJKV1QifQ.eyJlbnQiOjEsImV4cCI6MTc0MTY0OTk3OCwiaWQiOiIwMTkxZDY5NS0wZDQ3LTc3ZmItYmM1Zi01MTg1NTY4NDFiM2EiLCJpaWQiOjU5NDc3MTAzLCJvaWQiOjMzNDg0MCwicyI6MTAyNCwic2lkIjoiYjUxOTQ3NTUtYTQ2MS00MmEwLThiZDEtM2EyZTFjYjc1NzY1IiwidCI6ZmFsc2UsInVpZCI6NTk0NzcxMDN9.e8KyHVuWZWQQcuLQP3P_JNB1GQmjXvzAuHbaffuH3VJUa94H-uwvIq_T1LPXiiY-g2UPsZrJPKssng5qf8piDA")

# URL для запросов к API Wildberries
WILDBERRIES_API_URL = "https://supplies-api.wildberries.ru/api/v1"

# База данных пользователей (можно использовать SQLite, Redis или любую другую БД)
DATABASE_URL = os.path.join(os.getcwd(), 'db', 'users.db')
