# © 2025 Kaustav Ray. All rights reserved.
# Licensed under the MIT License.

"""
Telegram Bot with Mail.tm Integration
-------------------------------------
This bot allows users to:
- Create temporary email accounts
- Fetch all inbox messages (with pagination)
- View the full message body (decoded)

Features:
- Handles pagination (fetch full inbox, not just first page)
- Fetches each email’s body content by ID
- Error handling with logging
- Limits Telegram output length (avoids flooding)
"""

import logging
import requests
import html
import re
from uuid import uuid4
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# =======================
# Configuration
# =======================
API_URL = "https://api.mail.tm"
BOT_TOKEN = "7858331659:AAHaq-JszykJi9P_qksJIsx-401sgVIOPl4"  # Your Telegram bot token

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# =======================
# Mail.tm API Helpers
# =======================

def create_account() -> dict:
    """Create a temporary email account and return account details."""
    try:
        domain_resp = requests.get(f"{API_URL}/domains")
        domain_resp.raise_for_status()
        domains = domain_resp.json().get("hydra:member", [])
        if not domains:
            raise Exception("No domains available")
        domain = domains[0]["domain"]

        username = f"user{uuid4().hex[:8]}"
        password = uuid4().hex
        email = f"{username}@{domain}"

        payload = {"address": email, "password": password}
        resp = requests.post(f"{API_URL}/accounts", json=payload)
        resp.raise_for_status()

        token = login(email, password)
        return {"email": email, "password": password, "token": token}
    except Exception as e:
        logger.exception("Error creating account: %s", e)
        return {}


def login(email: str, password: str) -> str:
    """Login and return JWT token."""
    try:
        payload = {"address": email, "password": password}
        resp = requests.post(f"{API_URL}/token", json=payload)
        resp.raise_for_status()
        return resp.json()["token"]
    except Exception as e:
        logger.exception("Login failed for %s: %s", email, e)
        return ""


def fetch_all_messages(jwt_token: str) -> list[dict]:
    """Fetch all inbox messages by following pagination."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    url = f"{API_URL}/messages"
    all_messages = []

    try:
        while url:
            resp = requests.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            all_messages.extend(data.get("hydra:member", []))
            url = data.get("hydra:view", {}).get("hydra:next")
    except Exception as e:
        logger.exception("Error fetching messages: %s", e)

    return all_messages


def fetch_message_body(jwt_token: str, message_id: str) -> str:
    """Fetch full message body by ID."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    try:
        resp = requests.get(f"{API_URL}/messages/{message_id}", headers=headers)
        resp.raise_for_status()
        msg = resp.json()
        body = msg.get("text", "") or msg.get("html", [""])[0]

        # Decode HTML entities
        body = html.unescape(body)

        # Strip HTML tags if any
        body = re.sub(r"<.*?>", "", body)

        return body.strip() or "(empty message)"
    except Exception as e:
        logger.exception("Error fetching message body: %s", e)
        return "(error loading body)"


# =======================
# Telegram Bot Commands
# =======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Welcome to Temp Mail Bot!\n\n"
        "Commands:\n"
        "/getmail → Create a new temp email\n"
        "/inbox → Fetch your inbox (with full emails)\n"
    )


async def getmail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new temp email for the user."""
    account = create_account()
    if not account:
        await update.message.reply_text("❌ Failed to create email. Try again later.")
        return

    context.user_data["account"] = account
    await update.message.reply_text(
        f"✅ Your temp email is ready:\n\n📧 {account['email']}\n\n"
        f"Use /inbox to check messages."
    )


async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch inbox messages for the user (all pages, full body)."""
    account = context.user_data.get("account")
    if not account:
        await update.message.reply_text("⚠️ You need to create an email first using /getmail")
        return

    messages = fetch_all_messages(account["token"])
    if not messages:
        await update.message.reply_text("📭 Inbox is empty.")
        return

    for i, msg in enumerate(messages, start=1):
        sender = msg.get("from", {}).get("address", "Unknown")
        subject = msg.get("subject", "No subject")
        body = fetch_message_body(account["token"], msg["id"])

        text = (
            f"✉️ #{i}\n"
            f"From: {sender}\n"
            f"Subject: {subject}\n\n"
            f"{body[:3500]}"  # limit per Telegram message (~4096 chars max)
        )

        await update.message.reply_text(text)

        if i >= 10:  # safety cutoff
            await update.message.reply_text("... (showing first 10 messages only)")
            break


# =======================
# Bot Entry Point
# =======================

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("getmail", getmail))
    application.add_handler(CommandHandler("inbox", inbox))

    logger.info("Bot started 🚀")
    application.run_polling()


if __name__ == "__main__":
    main()
