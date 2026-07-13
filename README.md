# torah-loader

A tiny Claude Code add-on that turns loading time into learning time. It puts a
rotating piece of Torah / Parashat Hashavua learning in your status line while
Claude Code runs, so you pick up a verse or a teaching every time you glance
down.

One Python file, standard library only. No pip installs, no build step.

## What it does

- Fetches the current week's Torah portion (Parashat Hashavua) from
  [Sefaria's](https://www.sefaria.org) free public API.
- Prints one short line per status-line render: a source label plus a verse or
  teaching, kept under ~120 characters so it fits a terminal.
- Rotates the line over time so you see a different verse as you work.
- Caches the API response locally for 6 hours, so it does not hit the network
  on every render.
- Falls back to a bundled set of ~15 classic verses and teachings when there is
  no network, so the status line never breaks.
- Optional: fold in a bundled set of classic (secular) quotes, off by default.

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

## Rotation

The visible line advances roughly every 15 seconds. It is chosen from the
current portion's verses (or the fallback list) by a slowly-changing clock
value, so glancing down at different moments shows different learning without
jumping on every single render. Tune `ROTATE_SECONDS` at the top of the script
if you want it faster or slower.

## Optional: classic (secular) quotes

Off by default. When enabled, a small bundled set of classic quotes (Marcus
Aurelius, Seneca, Lao Tzu, and so on) is mixed into the rotation alongside the
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
