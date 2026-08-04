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
from atproto import Client, client_utils, models

RSS = "https://arquivolucyparsons.anarchistlibraries.net/feed"
STATE_PATH = Path(os.environ.get("STATE_PATH", "state.json"))

MAX_GRAPHEMES = 300
MAX_DESCRIPTION = 280
MAX_NEW_POSTS = 5
MAX_SEEN_IDS = 200
FALLBACK_LANG = "en"

# (cabeçalho, rodapé) por idioma. Para adicionar um idioma novo,
# basta acrescentar uma linha aqui.
STRINGS: dict[str, tuple[str, str]] = {
    "en": ("📚 New at the Lucy Parsons Archive", "Read online"),
    "pt": ("📚 Novo na Biblioteca Lucy Parsons", "Leia online"),
    "es": ("📚 Nuevo en la Biblioteca Lucy Parsons", "Leer en línea"),
    "fr": ("📚 Nouveau dans la Bibliothèque Lucy Parsons", "Lire en ligne"),
    "it": ("📚 Novità nella Biblioteca Lucy Parsons", "Leggi online"),
    "de": ("📚 Neu in der Lucy-Parsons-Bibliothek", "Online lesen"),
    "ca": ("📚 Nou a la Biblioteca Lucy Parsons", "Llegeix en línia"),
    "gl": ("📚 Novo na Biblioteca Lucy Parsons", "Ler en liña"),
    "eu": ("📚 Berria Lucy Parsons Liburutegian", "Irakurri sarean"),
    "nl": ("📚 Nieuw in de Lucy Parsons-bibliotheek", "Lees online"),
    "sv": ("📚 Nytt i Lucy Parsons-biblioteket", "Läs online"),
    "da": ("📚 Nyt i Lucy Parsons-biblioteket", "Læs online"),
    "no": ("📚 Nytt i Lucy Parsons-biblioteket", "Les på nett"),
    "fi": ("📚 Uutta Lucy Parsons -kirjastossa", "Lue verkossa"),
    "is": ("📚 Nýtt í Lucy Parsons-bókasafninu", "Lesa á netinu"),
    "pl": ("📚 Nowość w Bibliotece Lucy Parsons", "Czytaj online"),
    "cs": ("📚 Novinka v Knihovně Lucy Parsons", "Číst online"),
    "sk": ("📚 Novinka v Knižnici Lucy Parsons", "Čítať online"),
    "sl": ("📚 Novo v Knjižnici Lucy Parsons", "Beri na spletu"),
    "hr": ("📚 Novo u Knjižnici Lucy Parsons", "Čitaj online"),
    "sr": ("📚 Ново у Библиотеци Луси Парсонс", "Читај онлајн"),
    "bg": ("📚 Ново в Библиотека „Луси Парсънс“", "Чети онлайн"),
    "ru": ("📚 Новое в Библиотеке Люси Парсонс", "Читать онлайн"),
    "uk": ("📚 Нове в Бібліотеці Люсі Парсонс", "Читати онлайн"),
    "be": ("📚 Новае ў Бібліятэцы Люсі Парсанс", "Чытаць анлайн"),
    "el": ("📚 Νέο στη Βιβλιοθήκη Lucy Parsons", "Διαβάστε online"),
    "ro": ("📚 Nou în Biblioteca Lucy Parsons", "Citește online"),
    "hu": ("📚 Új a Lucy Parsons Könyvtárban", "Olvasás online"),
    "tr": ("📚 Lucy Parsons Kütüphanesi'nde yeni", "Çevrimiçi oku"),
    "lt": ("📚 Nauja Lucy Parsons bibliotekoje", "Skaityti internete"),
    "lv": ("📚 Jauns Lucy Parsons bibliotēkā", "Lasīt tiešsaistē"),
    "et": ("📚 Uus Lucy Parsonsi raamatukogus", "Loe veebis"),
    "sq": ("📚 E re në Bibliotekën Lucy Parsons", "Lexo online"),
    "mk": ("📚 Ново во Библиотеката Луси Парсонс", "Читај онлајн"),
    "eo": ("📚 Nova en la Biblioteko Lucy Parsons", "Legu rete"),
    "ar": ("📚 جديد في مكتبة لوسي بارسونز", "اقرأ على الإنترنت"),
    "he": ("📚 חדש בספריית לוסי פרסונס", "קראו באינטרנט"),
    "fa": ("📚 تازه در کتابخانه لوسی پارسونز", "آنلاین بخوانید"),
    "hi": ("📚 लूसी पार्सन्स पुस्तकालय में नया", "ऑनलाइन पढ़ें"),
    "bn": ("📚 লুসি পার্সন্স গ্রন্থাগারে নতুন", "অনলাইনে পড়ুন"),
    "ja": ("📚 ルーシー・パーソンズ図書館の新着", "オンラインで読む"),
    "ko": ("📚 루시 파슨스 도서관 신규 자료", "온라인으로 읽기"),
    "zh": ("📚 露西·帕森斯图书馆新增", "在线阅读"),
    "vi": ("📚 Mới trong Thư viện Lucy Parsons", "Đọc trực tuyến"),
    "th": ("📚 ใหม่ในห้องสมุด Lucy Parsons", "อ่านออนไลน์"),
    "id": ("📚 Baru di Perpustakaan Lucy Parsons", "Baca daring"),
    "ms": ("📚 Baharu di Perpustakaan Lucy Parsons", "Baca dalam talian"),
    "tl": ("📚 Bago sa Aklatan ng Lucy Parsons", "Basahin online"),
    "sw": ("📚 Mpya katika Maktaba ya Lucy Parsons", "Soma mtandaoni"),
    "af": ("📚 Nuut in die Lucy Parsons-biblioteek", "Lees aanlyn"),
    "ka": ("📚 ახალი ლუსი პარსონსის ბიბლიოთეკაში", "წაიკითხე ონლაინ"),
    "hy": ("📚 Նոր Լյուսի Փարսոնսի գրադարանում", "Կարդալ առցանց"),
    "ga": ("📚 Nua i Leabharlann Lucy Parsons", "Léigh ar líne"),
    "cy": ("📚 Newydd yn Llyfrgell Lucy Parsons", "Darllen ar-lein"),
}

# aliases e códigos regionais/legados que aparecem em feeds
LANG_ALIASES = {
    "iw": "he", "in": "id", "mo": "ro", "nb": "no", "nn": "no",
    "sh": "hr", "cn": "zh",
    "cat": "ca", "por": "pt", "spa": "es", "fra": "fr", "fre": "fr",
    "deu": "de", "ger": "de", "ita": "it", "eng": "en", "rus": "ru",
    "ell": "el", "gre": "el", "nld": "nl", "dut": "nl", "epo": "eo",
    "ara": "ar", "heb": "he", "jpn": "ja", "kor": "ko", "zho": "zh",
    "chi": "zh", "tur": "tr", "pol": "pl", "ces": "cs", "cze": "cs",
    "swe": "sv", "dan": "da", "nor": "no", "fin": "fi", "ukr": "uk",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lucyparsons-bot")


# --------------------------------------------------
# Utilidades
# --------------------------------------------------
def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_lang(raw) -> str | None:
    """'pt-BR', 'POR', 'fr_FR' -> 'pt', 'pt', 'fr' (ou None se desconhecido)."""
    if not raw:
        return None
    code = re.split(r"[-_]", str(raw).strip().lower())[0]
    code = LANG_ALIASES.get(code, code)
    return code if code in STRINGS else None


def get_language(entry, feed) -> str:
    """Descobre o idioma do texto: metadados > tag no título > idioma do feed."""
    candidates = [
        entry.get("language"),
        entry.get("dc_language"),
        entry.get("xml_lang"),
    ]
    for tag in entry.get("tags") or []:  # <category>fr</category>
        candidates.append(tag.get("term"))

    for raw in candidates:
        code = normalize_lang(raw)
        if code:
            return code

    # sufixo no título, ex.: "Título do texto (fr)" ou "[FR]"
    match = re.search(r"[(\[]([A-Za-z]{2,3})[)\]]\s*$", entry.get("title") or "")
    if match:
        code = normalize_lang(match.group(1))
        if code:
            return code

    code = normalize_lang((feed.feed or {}).get("language"))
    if code:
        return code

    return FALLBACK_LANG


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def get_author(entry) -> str:
    author = clean_html(entry.get("author") or "")
    if not author:
        authors = entry.get("authors") or []
        author = clean_html(authors[0].get("name", "")) if authors else ""
    return author


def get_summary(entry) -> str:
    for key in ("summary", "description"):
        text = clean_html(entry.get(key) or "")
        if text:
            return text
    content = entry.get("content") or []
    return clean_html(content[0].get("value", "")) if content else ""


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
    if not seen and state.get("last_id"):
        seen = [state["last_id"]]
    state["seen_ids"] = seen
    return state


def save_state(state: dict) -> None:
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
def build_text(entry, lang: str) -> client_utils.TextBuilder:
    """Com o embed card o link já aparece no card, então o texto fica limpo."""
    header, _ = STRINGS[lang]
    title = clean_html(entry.get("title", ""))
    author = get_author(entry)

    linha_autor = f"\n{author}" if author else ""
    orcamento = MAX_GRAPHEMES - len(header) - len(linha_autor) - 4
    title = truncate(title, max(20, orcamento))

    tb = client_utils.TextBuilder()
    tb.text(f"{header}\n\n{title}{linha_autor}")
    return tb


def build_embed(entry, lang: str) -> models.AppBskyEmbedExternal.Main:
    _, footer = STRINGS[lang]
    title = clean_html(entry.get("title", "")) or footer
    description = get_summary(entry) or footer
    return models.AppBskyEmbedExternal.Main(
        external=models.AppBskyEmbedExternal.External(
            uri=entry.link,
            title=truncate(title, 120),
            description=truncate(description, MAX_DESCRIPTION),
        )
    )


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

    novos = [
        e for e in feed.entries if (e.get("id") or e.get("link")) not in seen
    ][:MAX_NEW_POSTS]
    novos.reverse()  # do mais antigo para o mais novo

    if not novos:
        log.info("Nenhum artigo novo.")
        return 0

    client = Client()
    client.login(identifier, password)

    publicados = 0
    for entry in novos:
        entry_id = entry.get("id") or entry.get("link")
        lang = get_language(entry, feed)
        try:
            client.send_post(
                text=build_text(entry, lang),
                embed=build_embed(entry, lang),
                langs=[lang],
            )
        except Exception:
            log.exception("Falha ao publicar: %s", entry.get("title"))
            break  # não marca como visto; tenta de novo na próxima execução

        state["seen_ids"].insert(0, entry_id)
        publicados += 1
        log.info("Publicado [%s]: %s", lang, clean_html(entry.get("title", "")))

    state["seen_ids"] = state["seen_ids"][:MAX_SEEN_IDS]
    state["last_id"] = state["seen_ids"][0] if state["seen_ids"] else None
    save_state(state)

    return 0 if publicados else 1


if __name__ == "__main__":
    sys.exit(main())
