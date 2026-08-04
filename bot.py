import json
import feedparser

from atproto import Client

RSS = "https://arquivolucyparsons.anarchistlibraries.net/feed"

with open("state.json", "r", encoding="utf-8") as f:
    state = json.load(f)

feed = feedparser.parse(RSS)

entry = feed.entries[0]

article_id = entry.id

if article_id == state["last_id"]:
    print("Nenhum artigo novo.")
    quit()

title = entry.title
link = entry.link

text = f"""📚 New at the Lucy Parsons Archive

{title}

Read:
{link}
"""

import os

identifier = os.environ["BLUESKY_IDENTIFIER"]
password = os.environ["BLUESKY_PASSWORD"]

client = Client()

client.login(identifier, password)

client.send_post(text)

state["last_id"] = article_id

with open("state.json", "w", encoding="utf-8") as f:
    json.dump(state, f)

print("Publicado com sucesso.")
