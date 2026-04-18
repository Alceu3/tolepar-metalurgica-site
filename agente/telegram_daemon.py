"""Processo dedicado do bot Telegram da Evelyn."""
import time
import telegram_bot


def main():
    telegram_bot.start()
    # Mantem o processo vivo para a thread do bot nao morrer.
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
