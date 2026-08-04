import json
import os
import re

import feedparser
from atproto import Client, client_utils

RSS = "https://arquivolucyparsons.anarchistlibraries.net/feed"

# -------------------------
# Estado
# -------------------------

with open("state.json", "r", encoding="utf-8") as f:
    state = json.load(f)

feed = feedparser.parse(RSS)

entry = feed.entries[0]

article_id = entry.id

if article_id == state["last_id"]:
    print("Nenhum artigo novo.")
    quit()

# -------------------------
# Dados do artigo
# -------------------------

title = entry.title.strip()
link = entry.link

summary = ""

if hasattr(entry, "summary"):
    summary = re.sub("<.*?>", "", entry.summary)
    summary = re.sub(r"\s+", " ", summary).strip()

summary = summary[:180]

# -------------------------
# Bluesky
# -------------------------

client = Client()

client.login(
    os.environ["BLUESKY_IDENTIFIER"],
    os.environ["BLUESKY_PASSWORD"]
)

tb = client_utils.TextBuilder()

tb.text("📚 New at the Lucy Parsons Archive\n\n")

tb.text(title + "\n\n")

if summary:
    tb.text(summary + "\n\n")

tb.text("Read online:\n")

tb.link(link, link)

client.send_post(tb)

# -------------------------
# Atualiza estado
# -------------------------

state["last_id"] = article_id

with open("state.json", "w", encoding="utf-8") as f:
    json.dump(state, f)

print("Publicado:", title)
