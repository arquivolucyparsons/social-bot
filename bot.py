#!/usr/bin/env python3
"""Publica no Bluesky os novos artigos do feed da Biblioteca Lucy Parsons."""

from __future__ import annotations

import html
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path

import feedparser
from atproto import Client, client_utils

RSS = "https://arquivolucyparsons.anarchistlibraries.net/feed"
STATE_PATH = Path(os.environ.get("STATE_PATH", "state.json"))

MAX_GRAPHEMES = 300          # limite de um post no Bluesky
MAX_NEW_POSTS = 5            # evita flood se o feed "explodir"
MAX_SEEN_IDS = 200           # tamanho do histórico guardado

STRINGS = {
    "pt": ("📚 Novo na Biblioteca Lucy Parsons", "Leia online"),
    "es": ("📚 Nuevo en la Biblioteca Lucy Parsons", "Leer en línea"),
    "en": ("📚 New at the Lucy Parsons Archive", "Read online"),
}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("lucyparsons-bot")


# --------------------------------------------------
# Utilidades
# --------------------------------------------------
def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def get_language(entry) -> str:
    for value in (getattr(entry, "language", None), entry.get("dc_language")):
        if value:
            code = str(value).lower()[:2]
            if code in STRINGS:
                return code

    title = (entry.get("title") or "").lower()
    match = re.search(r"\((pt|en|es)\)", title)
    if match:
        return match.group(1)

    return "en"


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


# --------------------------------------------------
# Estado
# --------------------------------------------------
def load_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.warning("state.json não encontrado; começando do zero.")
        return {"seen_ids": []}
    except json.JSONDecodeError:
        log.warning("state.json inválido; começando do zero.")
        return {"seen_ids": []}

    seen = list(state.get("seen_ids") or [])
    # compatibilidade com o formato antigo
    if not seen and state.get("last_id"):
        seen = [state["last_id"]]
    state["seen_ids"] = seen
    return state


def save_state(state: dict) -> None:
    """Escrita atômica: não corrompe o arquivo se o processo morrer no meio."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=STATE_PATH.parent or ".", delete=False
    ) as tmp:
        json.dump(state, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(STATE_PATH)


# --------------------------------------------------
# Post
# --------------------------------------------------
def build_post(entry) -> client_utils.TextBuilder:
    header, footer = STRINGS[get_language(entry)]
    title = clean_html(entry.get("title", ""))
    link = entry.link

    # reserva espaço para o resto do post ao cortar o título
    fixed = len(header) + len(footer) + len(link) + 6
    title = truncate(title, max(20, MAX_GRAPHEMES - fixed))

    tb = client_utils.TextBuilder()
    tb.text(f"{header}\n\n{title}\n\n{footer}:\n")
    tb.link(link, link)
    return tb


def main() -> int:
    try:
        identifier = os.environ["BLUESKY_IDENTIFIER"]
        password = os.environ["BLUESKY_PASSWORD"]
    except KeyError as exc:
        log.error("Variável de ambiente faltando: %s", exc.args[0])
        return 1

    state = load_state()
    seen = set(state["seen_ids"])

    feed = feedparser.parse(RSS)
    if getattr(feed, "bozo", False):
        log.warning("Feed com problemas: %s", feed.get("bozo_exception"))
    if not feed.entries:
        log.info("RSS vazio ou inacessível.")
        return 0

    # do mais antigo para o mais novo, para a timeline ficar em ordem
    novos = [
        e for e in feed.entries if (e.get("id") or e.get("link")) not in seen
    ][:MAX_NEW_POSTS]
    novos.reverse()

    if not novos:
        log.info("Nenhum artigo novo.")
        return 0

    client = Client()
    client.login(identifier, password)

    publicados = 0
    for entry in novos:
        entry_id = entry.get("id") or entry.get("link")
        try:
            client.send_post(build_post(entry))
        except Exception:
            log.exception("Falha ao publicar: %s", entry.get("title"))
            break  # não marca como visto; tenta de novo na próxima execução

        state["seen_ids"].insert(0, entry_id)
        publicados += 1
        log.info("Publicado: %s", clean_html(entry.get("title", "")))

    state["seen_ids"] = state["seen_ids"][:MAX_SEEN_IDS]
    state["last_id"] = state["seen_ids"][0] if state["seen_ids"] else None
    save_state(state)

    return 0 if publicados else 1


if __name__ == "__main__":
    sys.exit(main())
