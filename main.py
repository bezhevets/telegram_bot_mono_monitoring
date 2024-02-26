import os
import time
import datetime

from typing import Callable, Any

from dotenv import load_dotenv

import requests
import telebot
from telebot import types
from telebot.formatting import escape_markdown

import pytz

load_dotenv()

bot = telebot.TeleBot(os.environ["TG_TOKEN"])
monobank_api_currency = "https://api.monobank.ua/bank/currency"
headers = {"X-Token": os.environ["MONO_TOKEN"]}


def get_list_id_users() -> list[int]:
    id_main_person_str = os.environ["ID_MAIN_PERSON"]
    list_id = list(map(int, id_main_person_str.split(",")))
    return list_id


ID_MAIN_PERSON = get_list_id_users()


def log_file(func: Callable) -> Callable:
    def inner(*args, **kwargs) -> Any:
        result = func(*args, **kwargs)
        message = f"{datetime.datetime.now().strftime('%H:%M:%S')} Успішно виконано {func.__doc__}"
        try:
            with open("log.txt", "a") as file:
                file.write(message + "\n")
        except Exception as e:
            print(f"Error log_file: {e}")
        return result

    return inner


@log_file
def info_currency() -> str:
    """Курс валют"""
    response = requests.get(monobank_api_currency)
    result = response.json()
    info = (
        f"usd: *Покупка:* {result[0]['rateBuy']} *Продаж:* {result[0]['rateSell']}"
        f"\neuro: *Покупка:* {result[1]['rateBuy']} *Продаж:* {result[1]['rateSell']}"
    )
    return info


def get_unix_time() -> int:
    today = datetime.datetime.now()
    start_time = datetime.time(hour=0, minute=1, second=0)
    today_with_time = datetime.datetime.combine(today.date(), start_time)
    return int(today_with_time.timestamp())


def formatted_time(unix_time) -> str:
    kiev_timezone = pytz.timezone("Europe/Kiev")
    kiev_time = unix_time.replace(tzinfo=pytz.utc).astimezone(kiev_timezone)
    return kiev_time.strftime("%H:%M:%S")


@log_file
def get_balance_fop() -> str:
    """Баланс ФОП рахунку"""
    try:
        monobank_statements = f"https://api.monobank.ua/personal/statement/{os.environ['FOP_ACC']}/{get_unix_time() - 86400}/"
        response = requests.get(monobank_statements, headers=headers)
        result = response.json()
        balance = f"*Ваш баланс:* {round(result[0]['balance'] / 100, 2)}"
        return balance
    except Exception as e:
        print(f"Error get_balance_fop: {e}")


@log_file
def get_statement(statement: list):
    """Виписка за сьогодні"""
    try:
        if not statement:
            return f"Сьогодні оплат ще не було 😕"
        else:
            message = "Виписка:"
            for i in range(len(statement)):
                message += (
                    f"\n\n{formatted_time(datetime.datetime.fromtimestamp(statement[i]['time'], datetime.timezone.utc))}"
                    f"\n*Сума*: {round(statement[i]['amount'] / 100, 2)}"
                    f"\n*Баланс*: {round(statement[i]['balance'] / 100, 2)}"
                    f"\n*Коментар*: {escape_markdown(statement[i].get('comment') or statement[i].get('description') or '-//-')}"
                )
            return message
    except Exception as e:
        print(f"Error in get_statement: {e}")


def get_statement_mono() -> list:
    monobank_statements = f"https://api.monobank.ua/personal/statement/{os.environ['FOP_ACC']}/{get_unix_time()}/"
    response = requests.get(monobank_statements, headers=headers)
    result = response.json()
    return result


def comparison_statements(statement_old) -> list | None:
    new_statement = get_statement_mono()
    if new_statement != statement_old:
        return new_statement


statement = get_statement_mono()


@log_file
def send_message() -> str | None:
    """Відправка сповіщення"""
    global statement

    result = get_statement_mono()

    if not result:
        statement = []
        return None
    elif result != statement:
        statement = result.copy()

        message = (
            f"{formatted_time(datetime.datetime.fromtimestamp(statement[0]['time'], datetime.timezone.utc))}"
            f"\n*Сума*: {round(statement[0]['amount'] / 100, 2)}"
            f"\n*Баланс*: {round(statement[0]['balance'] / 100, 2)}"
            f"\n*Коментар*: {escape_markdown(statement[0].get('comment') or statement[0].get('description') or '-//-')}"
        )
        return message
    else:
        return None


@bot.message_handler(commands=["start"])
def send_welcome(message) -> None:
    print(f"Start in time: {datetime.datetime.now()}")
    print(ID_MAIN_PERSON)
    if message.from_user.id not in list(ID_MAIN_PERSON):
        bot.send_message(
            message.chat.id,
            text="Доступ закритий. Ваш ID не в списку довірених",
        )
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1 = types.KeyboardButton("💵 Баланс")
        btn2 = types.KeyboardButton("🧾Виписка за сьогодні 💰")
        btn3 = types.KeyboardButton("❓ Курс Валют")
        markup.add(btn1, btn3)
        markup.add(btn2)
        bot.send_message(
            message.chat.id,
            text="Привіт, {0.first_name}!".format(message.from_user),
            reply_markup=markup,
        )
        while True:
            try:
                message_to_send = send_message()
                if message_to_send is not None:
                    try:
                        bot.send_message(
                            message.chat.id,
                            message_to_send,
                            parse_mode="Markdown",
                        )
                    except Exception as e:
                        print(f"Error bot.send_message: {e}")
                    time.sleep(300)
                else:
                    time.sleep(300)
            except Exception as e:
                print(f"Error in while loop: {e}")
                time.sleep(300)


@bot.message_handler(content_types=["text"])
def func(message) -> None:
    if message.text == "❓ Курс Валют":
        bot.send_message(
            message.chat.id, info_currency(), parse_mode="Markdown"
        )
    elif message.text == "💵 Баланс":
        bot.send_message(
            message.chat.id, get_balance_fop(), parse_mode="Markdown"
        )
    elif message.text == "🧾Виписка за сьогодні 💰":
        bot.send_message(
            message.chat.id,
            get_statement(statement),
            parse_mode="Markdown",
        )


if __name__ == "__main__":
    bot.infinity_polling()
