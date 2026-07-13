#!/usr/bin/env python3
"""
torah-loader: a Claude Code status line that shows Torah / parsha learning
while Claude Code runs.

Prints ONE short line per invocation. Sources content from Sefaria's free
public API (https://www.sefaria.org/api), caches it locally for a few hours,
and advances through the week's parsha verses IN ORDER, then through a bundled
set of divrei torah (short teachings from Rabbi Jonathan Sacks and others), so
it reads coherently instead of jumping around.

The status line is narrow, so long verses would get cut off. Instead of
truncating, the text SLIDES horizontally like a teleprompter: a fixed-width
window moves across the current item a few characters at a time, paced by real
elapsed time, so the whole verse becomes readable over several refreshes. When
one item has fully scrolled past, the next one begins at offset zero. Progress
is persisted in ~/.cache/torah-loader/state.json so it survives Claude Code's
irregular status-line refreshes.

Falls back to a small bundled list of verses when there is no network. Optional
secular classic quotes stay off by default behind the classic flag.

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
STATE_FILE = os.path.join(CACHE_DIR, "state.json")
CACHE_TTL_SECONDS = 6 * 60 * 60  # refresh from the network at most every 6h
NET_TIMEOUT_SECONDS = 4          # keep the status line snappy
MAX_LINE_CHARS = 120             # terminal-friendly length

# Teleprompter sliding. Claude Code refreshes the status line irregularly, so
# advancing is gated on real elapsed time rather than on render count.
SLIDE_INTERVAL_SECONDS = 2.5     # minimum real seconds between slide advances
SLIDE_STEP_CHARS = 8             # characters the window moves per advance
TRAILING_PAD_CHARS = 6           # blank tail after an item before the next one
TAG_MAX_CHARS = 28               # source-tag width cap at the front of the line

CALENDARS_URL = "https://www.sefaria.org/api/calendars"
TEXTS_URL = "https://www.sefaria.org/api/texts/{ref}?context=0"

# Toggle bundled classic (secular) quotes. Off by default. Enable with either
# the env var TORAH_LOADER_CLASSIC=1 or a config file (see below).
CLASSIC_ENV = "TORAH_LOADER_CLASSIC"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

# --- Bundled fallback content (used with no network) -----------------------
# Kept in a deliberate reading order so the fallback also reads coherently.

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

# Divrei torah: short teachings from Rabbi Jonathan Sacks and other well-known
# Torah thinkers. Default-on Torah content, folded into the rotation AFTER the
# week's parsha verses, in a fixed reading order. These are genuine, widely
# known ideas rendered as clearly attributed paraphrases (not invented exact
# quotations), with a couple of well-attested lines quoted as their authors
# said them.
DIVREI_TORAH = [
    ("Rabbi Jonathan Sacks", "To lead is to serve. A leader is measured by the dignity and freedom of the people they lift up."),
    ("Rabbi Jonathan Sacks", "Chosenness is not a privilege but a responsibility, a call to be a blessing to others."),
    ("Rabbi Jonathan Sacks", "The dignity of difference: God creates diversity, and no single people holds the whole of truth."),
    ("Rabbi Jonathan Sacks", "Faith is not certainty. Faith is the courage to live with uncertainty."),
    ("Rabbi Jonathan Sacks", "Judaism begins the day with gratitude, giving thanks before we ask for anything at all."),
    ("Hillel", "What is hateful to you, do not do to your neighbor. That is the whole Torah; the rest is commentary. Go and learn."),
    ("Maimonides (Rambam)", "The highest form of charity is to help a person become self-sufficient, so they need no charity at all."),
    ("Maimonides (Rambam)", "Give according to your means, and give with a cheerful face; the manner of giving matters as much as the gift."),
    ("Rabbi Akiva", "'Love your neighbor as yourself' is the great principle of the Torah."),
    ("Rabbi Akiva", "Beloved is humanity, for every person is created in the image of God."),
    ("Viktor Frankl", "When we can no longer change a situation, we are challenged to change ourselves."),
    ("Viktor Frankl", "Life is never made unbearable by circumstances, only by the lack of meaning and purpose."),
    ("Abraham Joshua Heschel", "Live in radical amazement. Get up in the morning and look at the world in a way that takes nothing for granted."),
    ("Abraham Joshua Heschel", "Wonder, not doubt, is the root of all knowledge."),
    ("Baal Shem Tov", "Forgetfulness leads to exile, while remembrance is the secret of redemption."),
    ("Baal Shem Tov", "The world is full of wonders, but we take our small hand and cover our eyes and see nothing."),
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
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&#39;", "'").replace("&quot;", '"')
    return " ".join(text.split())


def fetch_from_sefaria():
    """
    Returns {"label": <parsha name>, "verses": [(ref, text), ...]} in order.
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


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
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


def window_width(tag):
    """Characters of the sliding text window for a given source tag."""
    prefix = "\U0001f4d6 "  # open book
    head = "{}{}: ".format(prefix, truncate(tag, TAG_MAX_CHARS))
    return max(10, MAX_LINE_CHARS - len(head))


def slide_frame(key, pool):
    """
    Teleprompter position. Returns (idx, offset) for the current item and the
    left edge of the visible window into its text.

    Advances only once SLIDE_INTERVAL_SECONDS of real time have passed since the
    last advance (gated by a timestamp in state, because Claude Code refreshes
    the status line irregularly). Each advance moves the window right by
    SLIDE_STEP_CHARS. Once the window has revealed the end of the current item
    plus its trailing padding, the next item begins at offset zero. State resets
    to the first item when the content pool (key) or its length changes, so the
    reading always progresses in order.
    """
    now = time.time()
    n = len(pool)
    state = load_state()
    if state.get("key") == key and state.get("n") == n:
        idx = int(state.get("idx", 0)) % n
        offset = int(state.get("offset", 0))
        if now - float(state.get("advanced_at", 0)) >= SLIDE_INTERVAL_SECONDS:
            tag, text = pool[idx]
            width = window_width(tag)
            display_len = len(text) + TRAILING_PAD_CHARS
            if offset + width >= display_len:
                # The end of this item (with padding) is already in view: next.
                idx = (idx + 1) % n
                offset = 0
            else:
                offset += SLIDE_STEP_CHARS
            save_state({"key": key, "n": n, "idx": idx,
                        "offset": offset, "advanced_at": now})
        return idx, offset
    # New pool or first run: start at the beginning.
    save_state({"key": key, "n": n, "idx": 0, "offset": 0, "advanced_at": now})
    return 0, 0


def render():
    label, verses = get_content()

    # Default rotation: the week's parsha verses in order, then divrei torah.
    pool = list(verses)
    pool += [(src, txt) for src, txt in DIVREI_TORAH]
    # Classic secular quotes stay opt-in behind the classic flag.
    if classic_enabled():
        pool += [(who, quote) for who, quote in CLASSIC_QUOTES]

    if not pool:
        return "\U0001f4d6 Torah loading…"

    key = (label or "fallback") + "+divrei" + ("+classic" if classic_enabled() else "")
    idx, offset = slide_frame(key, pool)
    tag, text = pool[idx]

    prefix = "\U0001f4d6 "  # open book
    tag = truncate(tag, TAG_MAX_CHARS)
    head = "{}{}: ".format(prefix, tag)
    width = max(10, MAX_LINE_CHARS - len(head))

    # Slide a fixed-width window across the item, padded so it clears before the
    # next item starts.
    display = text + (" " * TRAILING_PAD_CHARS)
    window = display[offset:offset + width]
    return (head + window).rstrip()


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
