import json
import logging
import os
import sys
import time
import urllib.request
import urllib.parse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("SampleBot")

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logger.error("BOT_TOKEN is not set in environment!")
    sys.exit(1)

API_URL = f"https://api.telegram.org/bot{TOKEN}"

def call_api(method, params=None):
    url = f"{API_URL}/{method}"
    data = None
    if params:
        data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.error(f"API Error {method}: {exc}")
        return None

def send_message(chat_id, text):
    call_api("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def main():
    logger.info("Initializing Sample Test Bot...")
    me = call_api("getMe")
    if me and me.get("ok"):
        bot_user = me["result"]["username"]
        logger.info(f"Connected successfully as @{bot_user}!")
    else:
        logger.error("Failed to connect with provided BOT_TOKEN!")
        sys.exit(1)

    offset = 0
    logger.info("Started long polling loop. Ready for messages!")

    while True:
        try:
            updates = call_api("getUpdates", {"offset": offset, "timeout": 20})
            if updates and updates.get("ok"):
                for update in updates.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message")
                    if not msg:
                        continue

                    chat_id = msg["chat"]["id"]
                    first_name = msg.get("from", {}).get("first_name", "Friend")
                    text = msg.get("text", "")

                    logger.info(f"Received message from {first_name} (chat_id: {chat_id}): {text}")

                    if text.startswith("/start"):
                        send_message(
                            chat_id,
                            f"🎉 <b>Hello {first_name}!</b>\n\n"
                            f"I am a hosted test bot running on your platform! 🚀\n"
                            f"Type any message and I will reply instantly.",
                        )
                    else:
                        send_message(
                            chat_id,
                            f"🤖 <b>Test Bot Reply:</b>\n"
                            f"You said: <i>{text}</i>\n"
                            f"Status: 🟢 <b>Online & Hosted Successfully!</b>",
                        )
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Bot stopped by supervisor.")
            break
        except Exception as err:
            logger.error(f"Unexpected loop error: {err}")
            time.sleep(3)

if __name__ == "__main__":
    main()
