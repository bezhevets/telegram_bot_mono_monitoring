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


def get_statement_mono() -> list:
    monobank_statements = f"https://api.monobank.ua/personal/statement/{os.environ['FOP_ACC']}/{get_unix_time()}/"
    response = requests.get(monobank_statements, headers=headers)
    result = response.json()
    return result


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


def get_message_text(statement_detail: dict) -> str:
    text = (
        f"\n\n{formatted_time(datetime.datetime.fromtimestamp(statement_detail.get('time'), datetime.timezone.utc))}"
        f"\n*Сума*: {round(statement_detail.get('amount') / 100, 2)}"
        f"\n*Баланс*: {round(statement_detail.get('balance') / 100, 2)}"
        f"\n*Коментар*: {escape_markdown(statement_detail.get('comment') or statement_detail.get('description') or '-//-')}"
    )
    return text


@log_file
def get_statement(statements: list):
    """Виписка за сьогодні"""
    if not statements:
        return f"Сьогодні оплат ще не було 😕"
    else:
        message = "Виписка:"
        for stat in statements:
            message += get_message_text(stat)
        return message


@log_file
def send_message(statement) -> tuple:
    """Відправка сповіщення"""
    message = None
    result = get_statement_mono()

    if result:
        if result != statement:
            for detail in result:
                if detail not in statement:
                    if message:
                        message += get_message_text(detail)
                    else:
                        message = get_message_text(detail)
            statement = result.copy()
            return message, statement
    return message, statement


@bot.message_handler(commands=["start"])
def send_welcome(message) -> None:
    print(f"Start in time: {datetime.datetime.now()}")
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
            statement = []
            message_to_send, statement = send_message(statement)
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


@bot.message_handler(content_types=["text"])
def function_btn(message) -> None:
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
            get_statement(get_statement_mono()),
            parse_mode="Markdown",
        )


if __name__ == "__main__":
    bot.infinity_polling()
