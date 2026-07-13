# torah-loader

A tiny Claude Code add-on that turns loading time into learning time. It puts a
piece of Torah / Parashat Hashavua learning in your status line while Claude
Code runs, so you pick up a verse or a teaching every time you glance down.

One Python file, standard library only. No pip installs, no build step.

## What it does

- Fetches the current week's Torah portion (Parashat Hashavua) from
  [Sefaria's](https://www.sefaria.org) free public API.
- Prints one line per status-line render: a short source tag plus the text of
  the current verse or teaching.
- Slides long text horizontally like a teleprompter (see below), so nothing
  gets cut off. The status line is narrow, so instead of truncating a verse it
  scrolls the whole thing into view over a few seconds.
- Reads coherently and in order: verse 1 fully, then verse 2, and so on
  through the portion, then a bundled set of divrei torah.
- Caches the API response locally for 6 hours, so it does not hit the network
  on every render.
- Falls back to a bundled set of ~15 verses when there is no network, so the
  status line never breaks.
- Optional: fold in a bundled set of classic (secular) quotes, off by default.

## Teleprompter sliding

Each item scrolls left to right through a fixed-width window. Every couple of
seconds of real time (Claude Code refreshes the status line irregularly, so the
pace is gated on a timestamp, not on render count) the window advances a few
characters. Once a verse has fully scrolled past, the next one begins at the
start. A short source tag stays pinned at the front (the parsha reference or the
author) so you always know where the text is from. Reading progress is persisted
in `~/.cache/torah-loader/state.json`, so it picks up where it left off across
refreshes and sessions.

Tune the feel at the top of the script: `SLIDE_INTERVAL_SECONDS` (how often the
window moves), `SLIDE_STEP_CHARS` (how far it moves each time), and
`MAX_LINE_CHARS` (the total line width, which sets the window size).

## Divrei torah

After the week's parsha verses, the rotation moves through a bundled set of
short divrei torah: genuine, well-known teachings from Rabbi Jonathan Sacks
(covenant and conversation themes such as to lead is to serve, chosenness as
responsibility, and the dignity of difference) plus Hillel, Maimonides, Rabbi
Akiva, Viktor Frankl, Abraham Joshua Heschel, and the Baal Shem Tov. This Torah
content is on by default. The secular classic quotes below are separate and
stay opt-in.

## Install

1. Make sure the script is executable (already set, but to be safe):

   ```sh
   chmod +x /Users/jakegoldman/terso-ops/torah-loader/statusline.py
   ```

2. Add this to your `~/.claude/settings.json`. If you already have other keys,
   just add the `statusLine` block:

   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "/Users/jakegoldman/terso-ops/torah-loader/statusline.py"
     }
   }
   ```

   If you move the folder, update that path. On a system where `python3` is not
   on the shebang path, use the explicit form instead:

   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "python3 /Users/jakegoldman/terso-ops/torah-loader/statusline.py"
     }
   }
   ```

3. Restart Claude Code (or start a new session). The verse shows up in the
   status line.

## How caching works

The script keeps one JSON cache at `~/.cache/torah-loader/cache.json`. On each
render it reads that file first. If the cache is newer than 6 hours it uses it
directly and makes no network call. Once the cache is older than 6 hours, the
next render fetches fresh data from Sefaria and rewrites the cache. Network
calls time out after 4 seconds, and any failure falls back to the bundled
verses, so a slow or missing connection never stalls or breaks your prompt.

To force a refresh, delete the cache file:

```sh
rm ~/.cache/torah-loader/cache.json
```

## Optional: classic (secular) quotes

Off by default. When enabled, a small bundled set of classic quotes (Marcus
Aurelius, Seneca, Lao Tzu, and so on) is appended to the rotation after the
Torah content. Turn it on either way:

- Environment variable:

  ```sh
  export TORAH_LOADER_CLASSIC=1
  ```

- Or a config file next to the script at
  `/Users/jakegoldman/terso-ops/torah-loader/config` with a single line:

  ```
  classic=on
  ```

  A ready-to-copy `config.example` ships in this folder. Copy it to `config`
  and edit.

## License and data

MIT licensed. See `LICENSE`.

Torah and classic-text content comes from the free
[Sefaria API](https://www.sefaria.org/api). Sefaria's texts are largely public
domain or openly licensed; check their [terms](https://www.sefaria.org/terms)
for specifics. This tool is not affiliated with Sefaria.
