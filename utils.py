import logging
import requests
from config import WILDBERRIES_API_URL, WILDBERRIES_API_KEY


# Функция для получения списка складов
def get_warehouses():
    headers = {
        "Authorization": f"{WILDBERRIES_API_KEY}",  # Добавляем HeaderApiKey перед ключом
        "Content-Type": "application/json",  # Этот заголовок также указан в Postman
        "User-Agent": "Googlebot"  # Используем тот же User-Agent, что и в Postman
    }
    try:
        response = requests.get(f"{WILDBERRIES_API_URL}/warehouses", headers=headers)
        if response.status_code == 200:
            # Возвращаем JSON-ответ
            return response.json()
        else:
            logging.error(f"Ошибка при получении складов: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        logging.error(f"Ошибка при запросе: {e}")

    return None


# Функция для получения коэффициентов приемки
def get_acceptance_coefficients(warehouse_ids):
    url = f"{WILDBERRIES_API_URL}/acceptance/coefficients"
    headers = {
        "Authorization": f"{WILDBERRIES_API_KEY}",
        "Content-Type": "application/json"
    }
    params = {
        "warehouseIDs": ",".join(map(str, warehouse_ids))
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Ошибка при получении коэффициентов приемки: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        logging.error(f"Ошибка при отправке запроса: {e}")

    return None
