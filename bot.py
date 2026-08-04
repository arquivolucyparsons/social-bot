import json
import os
import re

import feedparser
from atproto import Client, client_utils

RSS = "https://arquivolucyparsons.anarchistlibraries.net/feed"


# --------------------------------------------------
# Utilidades
# --------------------------------------------------

def clean_html(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_language(entry):
    if hasattr(entry, "language"):
        lang = str(entry.language).lower()

        if lang.startswith("pt"):
            return "pt"

        if lang.startswith("en"):
            return "en"

        if lang.startswith("es"):
            return "es"

    title = entry.title.lower()

    if "(pt)" in title:
        return "pt"

    if "(en)" in title:
        return "en"

    if "(es)" in title:
        return "es"

    return "en"


# --------------------------------------------------
# Estado
# --------------------------------------------------

with open("state.json", "r", encoding="utf-8") as f:
    state = json.load(f)

feed = feedparser.parse(RSS)

if not feed.entries:
    print("RSS vazio.")
    quit()

entry = feed.entries[0]

article_id = entry.id

if article_id == state.get("last_id"):
    print("Nenhum artigo novo.")
    quit()

title = clean_html(entry.title)
link = entry.link

lang = get_language(entry)

# --------------------------------------------------
# Texto
# --------------------------------------------------

if lang == "pt":
    header = "📚 Novo na Biblioteca Lucy Parsons"
    footer = "Leia online"

elif lang == "es":
    header = "📚 Nuevo en la Biblioteca Lucy Parsons"
    footer = "Leer en línea"

else:
    header = "📚 New at the Lucy Parsons Archive"
    footer = "Read online"

# --------------------------------------------------
# Bluesky
# --------------------------------------------------

tb = client_utils.TextBuilder()

tb.text(header)
tb.text("\n\n")

tb.text(title)
tb.text("\n\n")

tb.text(footer)
tb.text(":\n")

tb.link(link, link)

client = Client()

client.login(
    os.environ["BLUESKY_IDENTIFIER"],
    os.environ["BLUESKY_PASSWORD"],
)

client.send_post(tb)

# --------------------------------------------------
# Atualiza estado
# --------------------------------------------------

state["last_id"] = article_id

with open("state.json", "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)

print("Publicado:", title)
