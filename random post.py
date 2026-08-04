#!/usr/bin/env python3
"""Sorteia um texto do acervo da Biblioteca Lucy Parsons e publica no Bluesky.

Usa a tabela de idiomas e as utilidades do bot.py, então os dois compartilham
a mesma lógica de tradução, truncamento e estado.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from atproto import Client, client_utils, models

from bot import (
    MAX_DESCRIPTION,
    MAX_GRAPHEMES,
    STRINGS,
    clean_html,
    normalize_lang,
    save_state,
    truncate,
)

BASE = "https://arquivolucyparsons.anarchistlibraries.net"
SITEMAP = f"{BASE}/sitemap.txt"
HISTORY_PATH = Path(os.environ.get("RANDOM_STATE_PATH", "random_state.json"))
HISTORY_SIZE = 300  # não repete um texto sorteado nas últimas N vezes
TIMEOUT = 30
FALLBACK_LANG = "en"

# "Do baú do arquivo" por idioma — cai no inglês se faltar tradução
THROWBACK = {
    "en": "🕰️ From the archive’s vault",
    "pt": "🕰️ Do baú do arquivo",
    "es": "🕰️ Del baúl del archivo",
    "fr": "🕰️ Du fonds des archives",
    "it": "🕰️ Dal baule dell’archivio",
    "de": "🕰️ Aus der Truhe des Archivs",
    "ca": "🕰️ Del bagul de l’arxiu",
    "gl": "🕰️ Do baúl do arquivo",
    "nl": "🕰️ Uit het archief",
    "sv": "🕰️ Ur arkivets kista",
    "pl": "🕰️ Ze skarbca archiwum",
    "cs": "🕰️ Z truhly archivu",
    "ru": "🕰️ Из архивных запасников",
    "uk": "🕰️ Зі скрині архіву",
    "el": "🕰️ Από το αρχείο",
    "tr": "🕰️ Arşivin sandığından",
    "eo": "🕰️ El la kesto de la arkivo",
    "ar": "🕰️ من صندوق الأرشيف",
    "ja": "🕰️ アーカイブの蔵出し",
    "zh": "🕰️ 档案库藏",
    "id": "🕰️ Dari lemari arsip",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lucyparsons-random")

session = requests.Session()
session.headers["User-Agent"] = "lucyparsons-bot/1.0 (+bluesky feed bot)"


# --------------------------------------------------
# Acervo
# --------------------------------------------------
def list_texts() -> list[str]:
    """Todas as URLs de texto do acervo, a partir do sitemap do Amusewiki."""
    resp = session.get(SITEMAP, timeout=TIMEOUT)
    resp.raise_for_status()

    urls = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line.startswith("http"):
            continue
        path = urlparse(line).path
        # só páginas de texto: /library/<uri>, sem .html/.pdf/.epub etc.
        if re.fullmatch(r"/library/[a-z0-9-]+", path):
            urls.append(line)
    return urls


DIRECTIVE = re.compile(r"^#(\w+)\s+(.*)$")


def fetch_metadata(url: str) -> dict:
    """Lê o fonte .muse do texto e extrai as diretivas do cabeçalho."""
    resp = session.get(url + ".muse", timeout=TIMEOUT)
    resp.raise_for_status()

    meta: dict[str, str] = {}
    for line in resp.text.splitlines():
        if not line.strip():
            if meta:  # cabeçalho terminou
                break
            continue
        match = DIRECTIVE.match(line)
        if match:
            key, value = match.group(1).lower(), match.group(2).strip()
            meta[key] = value
        elif line.startswith(" ") and meta:
            meta[list(meta)[-1]] += " " + line.strip()  # continuação
        else:
            break
    return meta


# --------------------------------------------------
# Histórico
# --------------------------------------------------
def load_history() -> list[str]:
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return list(data.get("recent") or [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


# --------------------------------------------------
# Post
# --------------------------------------------------
def build_post(url: str, meta: dict):
    lang = normalize_lang(meta.get("lang")) or FALLBACK_LANG
    header = THROWBACK.get(lang, THROWBACK[FALLBACK_LANG])
    _, footer = STRINGS[lang]

    title = clean_html(meta.get("title", "")) or url.rsplit("/", 1)[-1]
    subtitle = clean_html(meta.get("subtitle", ""))
    author = clean_html(meta.get("author", ""))
    date = clean_html(meta.get("date", ""))
    teaser = clean_html(meta.get("teaser", "")) or subtitle or footer

    linhas = [header, "", title]
    if author:
        linhas.append(f"{author}{f' ({date})' if date else ''}")
    texto = "\n".join(linhas)

    if len(texto) > MAX_GRAPHEMES:
        title = truncate(title, len(title) - (len(texto) - MAX_GRAPHEMES))
        linhas[2] = title
        texto = "\n".join(linhas)

    tb = client_utils.TextBuilder()
    tb.text(texto)

    embed = models.AppBskyEmbedExternal.Main(
        external=models.AppBskyEmbedExternal.External(
            uri=url,
            title=truncate(f"{title}{f' — {author}' if author else ''}", 120),
            description=truncate(teaser, MAX_DESCRIPTION),
        )
    )
    return tb, embed, lang


def main() -> int:
    try:
        identifier = os.environ["BLUESKY_IDENTIFIER"]
        password = os.environ["BLUESKY_PASSWORD"]
    except KeyError as exc:
        log.error("Variável de ambiente faltando: %s", exc.args[0])
        return 1

    try:
        urls = list_texts()
    except requests.RequestException:
        log.exception("Não consegui ler o sitemap.")
        return 1

    if not urls:
        log.error("Nenhum texto encontrado no sitemap.")
        return 1

    recent = load_history()
    candidatos = [u for u in urls if u not in set(recent)] or urls
    log.info("%d textos no acervo, %d elegíveis.", len(urls), len(candidatos))

    escolhido = None
    for url in random.sample(candidatos, min(5, len(candidatos))):
        try:
            meta = fetch_metadata(url)
        except requests.RequestException:
            log.warning("Falha ao ler %s, tentando outro.", url)
            continue
        if meta.get("deleted") or not meta.get("title"):
            continue
        escolhido = (url, meta)
        break

    if not escolhido:
        log.error("Não consegui obter metadados de nenhum candidato.")
        return 1

    url, meta = escolhido
    tb, embed, lang = build_post(url, meta)

    client = Client()
    client.login(identifier, password)
    client.send_post(text=tb, embed=embed, langs=[lang])

    recent.insert(0, url)
    save_state({"recent": recent[:HISTORY_SIZE]}, HISTORY_PATH)
    log.info("Publicado [%s]: %s", lang, meta.get("title"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
