#!/usr/bin/env python3
"""
torah-loader: a Claude Code status line that shows a rotating piece of
Torah / parsha learning while Claude Code runs.

Prints ONE short line per invocation. Sources content from Sefaria's free
public API (https://www.sefaria.org/api), caches it locally for a few hours,
rotates through verses over time, and falls back to a small bundled list of
classic teachings when there is no network.

Python 3, standard library only. No pip installs. MIT licensed.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

# --- Configuration ---------------------------------------------------------

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "torah-loader")
CACHE_FILE = os.path.join(CACHE_DIR, "cache.json")
CACHE_TTL_SECONDS = 6 * 60 * 60  # refresh from the network at most every 6h
NET_TIMEOUT_SECONDS = 4          # keep the status line snappy
MAX_LINE_CHARS = 120             # terminal-friendly length
ROTATE_SECONDS = 15              # advance to the next line roughly this often

CALENDARS_URL = "https://www.sefaria.org/api/calendars"
TEXTS_URL = "https://www.sefaria.org/api/texts/{ref}?context=0"

# Toggle bundled classic (secular) quotes. Off by default. Enable with either
# the env var TORAH_LOADER_CLASSIC=1 or a config file (see below).
CLASSIC_ENV = "TORAH_LOADER_CLASSIC"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

# --- Bundled fallback content (used with no network) -----------------------

FALLBACK_VERSES = [
    ("Genesis 1:1", "In the beginning God created the heaven and the earth."),
    ("Leviticus 19:18", "Love your neighbor as yourself."),
    ("Deuteronomy 6:5", "You shall love the Lord your God with all your heart, soul, and might."),
    ("Deuteronomy 16:20", "Justice, justice shall you pursue."),
    ("Micah 6:8", "Do justly, love mercy, and walk humbly with your God."),
    ("Psalms 118:24", "This is the day the Lord has made; let us rejoice and be glad in it."),
    ("Psalms 23:1", "The Lord is my shepherd; I shall not want."),
    ("Proverbs 3:6", "In all your ways acknowledge Him, and He will direct your paths."),
    ("Ecclesiastes 3:1", "To everything there is a season, and a time to every purpose under heaven."),
    ("Pirkei Avot 1:14", "If I am not for myself, who is for me? If not now, when? (Hillel)"),
    ("Pirkei Avot 2:16", "You are not obligated to complete the work, but neither are you free to desist from it."),
    ("Pirkei Avot 4:1", "Who is wise? One who learns from every person."),
    ("Isaiah 1:17", "Learn to do good; seek justice, relieve the oppressed."),
    ("Numbers 6:24", "May the Lord bless you and keep you."),
    ("Exodus 23:9", "You know the heart of a stranger, for you were strangers in the land of Egypt."),
]

# Optional classic (secular) quotes. Only shown when classic mode is enabled.
CLASSIC_QUOTES = [
    ("Marcus Aurelius", "You have power over your mind, not outside events. Realize this, and you will find strength."),
    ("Seneca", "We suffer more often in imagination than in reality."),
    ("Lao Tzu", "A journey of a thousand miles begins with a single step."),
    ("Confucius", "It does not matter how slowly you go as long as you do not stop."),
    ("Heraclitus", "No man ever steps in the same river twice."),
    ("Epictetus", "It's not what happens to you, but how you react to it that matters."),
    ("Aristotle", "We are what we repeatedly do. Excellence, then, is not an act but a habit."),
    ("Socrates", "The only true wisdom is in knowing you know nothing."),
    ("Viktor Frankl", "Between stimulus and response there is a space; in that space is our power to choose."),
    ("Montaigne", "My life has been full of terrible misfortunes, most of which never happened."),
]


# --- Helpers ---------------------------------------------------------------

def classic_enabled():
    """Classic quotes on if env var is truthy or config file requests it."""
    val = os.environ.get(CLASSIC_ENV, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    if key.strip().lower() == "classic":
                        return value.strip().lower() in ("1", "true", "yes", "on")
    except OSError:
        pass
    return False


def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "torah-loader/1.0"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def clean_text(raw):
    """Strip HTML tags / footnote markup Sefaria sometimes returns."""
    if isinstance(raw, list):
        raw = " ".join(str(x) for x in raw)
    text = str(raw)
    # crude tag strip, stdlib only
    out = []
    depth = 0
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            if depth > 0:
                depth -= 1
        elif depth == 0:
            out.append(ch)
    text = "".join(out)
    # collapse whitespace and common entities
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&#39;", "'").replace("&quot;", '"')
    return " ".join(text.split())


def fetch_from_sefaria():
    """
    Returns a dict: {"label": <parsha name>, "verses": [(ref, text), ...]}.
    Raises on network / parse failure so callers can fall back.
    """
    cal = http_get_json(CALENDARS_URL)
    parsha_ref = None
    parsha_name = None
    for item in cal.get("calendar_items", []):
        title = item.get("title", {})
        if title.get("en") == "Parashat Hashavua":
            parsha_ref = item.get("ref")
            parsha_name = item.get("displayValue", {}).get("en") or "Parasha"
            break
    if not parsha_ref:
        raise ValueError("no parasha ref in calendars response")

    data = http_get_json(TEXTS_URL.format(ref=urllib.parse.quote(parsha_ref)))
    english = data.get("text") or data.get("he") or []

    # A multi-chapter parasha ref comes back as a list of lists (one inner
    # list per chapter). Flatten to individual verse strings.
    def flatten(node):
        if isinstance(node, str):
            return [node]
        out = []
        for item in node:
            out.extend(flatten(item))
        return out

    segments = flatten(english)
    verses = []
    for idx, seg in enumerate(segments, start=1):
        cleaned = clean_text(seg)
        if cleaned:
            verses.append(("{} #{}".format(parsha_name, idx), cleaned))
    if not verses:
        raise ValueError("no verses parsed from texts response")
    return {"label": parsha_name, "verses": verses}


def load_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        if time.time() - blob.get("fetched_at", 0) < CACHE_TTL_SECONDS:
            return blob.get("data")
    except (OSError, ValueError):
        pass
    return None


def save_cache(data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump({"fetched_at": time.time(), "data": data}, fh)
    except OSError:
        pass


def get_content():
    """Return (source_label, verses_list). Uses cache, then network, then fallback."""
    cached = load_cache()
    if cached and cached.get("verses"):
        return cached["label"], [tuple(v) for v in cached["verses"]]
    try:
        data = fetch_from_sefaria()
        save_cache(data)
        return data["label"], data["verses"]
    except Exception:
        return None, list(FALLBACK_VERSES)


def truncate(text, limit):
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def render():
    label, verses = get_content()

    # Optionally fold in classic quotes.
    pool = list(verses)
    if classic_enabled():
        pool += [("{}".format(who), quote) for who, quote in CLASSIC_QUOTES]

    if not pool:
        return "\U0001f4d6 Torah loading…"

    # Rotate based on a slowly-changing clock value.
    idx = int(time.time() // ROTATE_SECONDS) % len(pool)
    ref, text = pool[idx]

    prefix = "\U0001f4d6 "  # open book
    # Budget: prefix + "ref: " + text, all under MAX_LINE_CHARS.
    ref = truncate(ref, 40)
    head = "{}{}: ".format(prefix, ref)
    remaining = MAX_LINE_CHARS - len(head)
    line = head + truncate(text, max(10, remaining))
    return line


def main():
    # Claude Code passes session JSON on stdin; we don't need it, but drain it.
    try:
        if not sys.stdin.isatty():
            sys.stdin.read()
    except Exception:
        pass
    try:
        print(render())
    except Exception:
        # Never break the status line.
        ref, text = FALLBACK_VERSES[0]
        print("\U0001f4d6 {}: {}".format(ref, text))


if __name__ == "__main__":
    main()
