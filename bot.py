import json
import os
import re

import feedparser
from atproto import Client, client_utils

RSS = "https://arquivolucyparsons.anarchistlibraries.net/feed"
MAX_CHARS = 300


# --------------------------------------------------
# Utilidades
# --------------------------------------------------

def clean_html(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_language(entry):
    if hasattr(entry, "language"):
        lang = entry.language.lower()

        if lang.startswith("pt"):
            return "pt"

        if lang.startswith("en"):
            return "en"

    title = entry.title.lower()

    if title.endswith("(pt)"):
        return "pt"

    if title.endswith("(en)"):
        return "en"

    return "en"


# --------------------------------------------------
# Estado
# --------------------------------------------------

with open("state.json", "r", encoding="utf-8") as f:
    state = json.load(f)

feed = feedparser.parse(RSS)

if len(feed.entries) == 0:
    print("RSS vazio.")
    quit()

entry = feed.entries[0]

article_id = entry.id

if article_id == state["last_id"]:
    print("Nenhum artigo novo.")
    quit()

title = clean_html(entry.title)
link = entry.link

summary = ""

if hasattr(entry, "summary"):
    summary = clean_html(entry.summary)

lang = get_language(entry)

# --------------------------------------------------
# Monta o post
# --------------------------------------------------

tb = client_utils.TextBuilder()

if lang == "pt":
    header = "📚 Novo na Biblioteca Lucy Parsons"
    footer = "Leia online:"
else:
    header = "📚 New at the Lucy Parsons Archive"
    footer = "Read online:"

tb.text(header + "\n\n")
tb.text(title + "\n\n")

fixed_text = header + "\n\n" + title + "\n\n" + footer + "\n"

available = MAX_CHARS - len(fixed_text) - len(link)

if available < 0:
    available = 0

if summary:

    if len(summary) > available:
        summary = summary[: available - 3].rstrip() + "..."

    tb.text(summary + "\n\n")

tb.text(footer + "\n")

tb.link(link, link)

# --------------------------------------------------
# Publica
# --------------------------------------------------

client = Client()

client.login(
    os.environ["BLUESKY_IDENTIFIER"],
    os.environ["BLUESKY_PASSWORD"]
)

client.send_post(tb)

# --------------------------------------------------
# Atualiza estado
# --------------------------------------------------

state["last_id"] = article_id

with open("state.json", "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)

print("Publicado:", title)
