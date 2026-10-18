# YouTube Music Bulk Import

Import text-file playlists into YouTube Music. Each `.txt` file becomes a
separate playlist, with the filename (without `.txt`) used as its title.

## Quick start (`uvx` / `pipx`)

You can run `ytm-import` on any machine with [uv](https://docs.astral.sh/uv/) or
[pipx](https://pipx.pypa.io/) without cloning the repository or creating a
virtual environment.

Run directly from GitHub in a directory containing your `.txt` playlist files
(or pass `.txt` files / directories as arguments):

```sh
uvx --from git+https://github.com/valentinsviridov/ytm-import ytm-import
```

Or with `pipx`:

```sh
pipx run --spec git+https://github.com/valentinsviridov/ytm-import ytm-import
```

You can also pass specific `.txt` files or directories:

```sh
uvx --from git+https://github.com/valentinsviridov/ytm-import ytm-import Jazz.txt Grunge.txt
```

- **First-run authentication:** If no `browser.json` credentials exist yet,
  `ytm-import` interactively prompts you to paste your YouTube Music browser
  request headers, saves them to your user config directory
  (`~/.config/ytm-import/browser.json`, or `%APPDATA%\ytm-import\browser.json`
  on Windows), and immediately proceeds with the import.
- **Persistent search cache:** Search results are cached in your user cache
  directory (`~/.cache/ytm-import/search_cache.json`, or
  `%LOCALAPPDATA%\ytm-import\search_cache.json` on Windows) so subsequent runs
  from any folder reuse cached matches. (If `./browser.json` or
  `./search_cache.json` exists in the current directory, it is used instead.)
- **Re-authenticating:** Pass `--reauth` at any time if your browser session
  expires.

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) or [pipx](https://pipx.pypa.io/).
- A YouTube Music account signed in through your browser.

The project supports Python 3.10 or newer. `.python-version` selects Python 3.14
for local development; uv can download it automatically if needed.

## Project structure

```text
ytm-import/
├── .python-version
├── pyproject.toml
├── uv.lock
├── README.md
├── src/
│   └── ytm_import/
│       ├── cli.py        # Command-line arguments and authentication
│       ├── client.py     # API client interface
│       ├── config.py     # Import settings
│       ├── matching.py   # Text normalization and candidate scoring
│       ├── search.py     # Search, caching, and retries
│       ├── storage.py    # Playlist and cache files
│       └── importer.py   # Track selection and import orchestration
├── tests/
├── browser.json          # Optional local credentials override
└── playlists/
    ├── README.md
    ├── Jazz.txt
    ├── Grunge.txt
    └── Ambient.txt
```

## Local setup (when running from a clone)

Open a terminal in the project directory and install the locked dependencies:

```sh
uv sync --locked
```

uv creates a local `.venv` and installs this package, `ytmusicapi`, and the
development dependencies. You can run commands with `uv run` without activating
the virtual environment. See the
[uv project guide](https://docs.astral.sh/uv/guides/projects/) for details.

In IntelliJ IDEA or PyCharm, select this project's `.venv/bin/python`
(`.venv\Scripts\python.exe` on Windows) as the Python SDK/interpreter so code
inspections use the project's Python version and installed packages. See the
[JetBrains Python SDK guide](https://www.jetbrains.com/help/idea/configuring-python-sdk.html).
IDE settings stay local and are excluded from version control.

## Authentication details

On your first run (or when running `ytm-import --reauth` or
`uv run ytmusicapi browser`), you will be prompted with
`Please paste the request headers from Firefox or Chrome/Edge and press Ctrl-D to continue:`.
Copy the **Request Headers** from an authenticated YouTube Music API call:

1. Open [YouTube Music](https://music.youtube.com) in Firefox, Chrome, or Edge and make sure you are signed in.
2. Open Developer Tools (`F12` or `Ctrl+Shift+I` on Linux/Windows, `Cmd+Option+I` on macOS) and switch to the **Network** tab.
3. Type `browse` into the Network filter box, then click **Library** or **Home** in YouTube Music so a new request appears.
4. Click an authenticated `POST` request to `music.youtube.com` whose path starts with `/youtubei/v1/browse` (status `200`).
5. Open that request's **Headers** tab and locate the **Request Headers** section (do **not** use "Copy as cURL", "Copy as fetch", or **Response Headers**):
   - **Firefox**: Enable the **Raw** toggle on the **Request Headers** section, then select and copy the `Key: Value` header lines under **Request Headers** (omitting the first `POST /youtubei/v1/browse... HTTP/2` request line; `ytm-import` also strips that line automatically if included).
   - **Chrome / Edge**: In the **Request Headers** section, select and copy all header lines directly from the panel (from the first header down to the last).
   - Make sure the copied headers include `authorization` (starting with `SAPISIDHASH`), `cookie` (containing `__Secure-3PAPISID`), and `x-goog-authuser`.
6. Paste the copied headers into the terminal, press `Enter`, and press `Ctrl-D` (or `Enter`, `Ctrl-Z`, `Enter` on Windows) to save `browser.json`.

See the
[ytmusicapi browser authentication guide](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html)
for additional troubleshooting details.

`browser.json` contains your browser session credentials. Do not share it or
upload it to cloud storage or GitHub. It is excluded by `.gitignore`.

## Prepare your playlists

Place your `.txt` files in a `playlists/` directory, in the current working
directory, or pass their paths directly on the command line. Use one song per
line, preferably including both the artist and song title:

```text
Miles Davis — So What
John Coltrane — A Love Supreme
The Dave Brubeck Quartet — Take Five
```

Numbering such as `1. ` or `12) ` is allowed; the script removes it. Empty lines
are ignored. UTF-8 (with or without a byte order mark) and Windows-1251 files are
supported.

## Run the import

Start with one or two copies of your playlist files to check the results, then
run the full import:

```sh
uv run ytm-import
```

`uv run python -m ytm_import` also works.

- By default, `ytm-import` reads `.txt` files from `./playlists` if that
  directory exists, or falls back to `.txt` files in the current directory. You
  can also pass `.txt` files or directories as positional arguments.
- The filename without `.txt` becomes the playlist title.
- Playlists are created as `PRIVATE` by default.
- An existing playlist you own with the same title is continued, ignoring case.
- Existing playlist contents are read in full; only missing tracks are added.
- Tracks with uncertain matches and duplicate matches are skipped.
- The import report is written to `import_report.csv` and replaced on each run.
- `search_cache.json` is saved atomically before each track is added. Cached
  matches and exact playlist metadata matches avoid repeated searches.
- A playlist is created only if at least one track meets the confidence threshold.

If an import is interrupted or a request fails, rerun the same command to
continue. Songs are added incrementally, and the next run checks what is already
in YouTube Music, including additions whose responses were lost. Repeating an
import does not create another playlist or add the same video ID twice. You can
also append songs to a file and rerun the command to add them to its playlist.
Keep `search_cache.json` between runs to avoid searching again for source lines
whose wording differs from the playlist's track titles and artist names.

Local playlist files, credentials, reports, and the search cache are excluded
by `.gitignore`. Keep `pyproject.toml`, `.python-version`, and `uv.lock` in
version control.

## Playlist visibility

To create unlisted or public playlists, pass `--privacy`:

```sh
uv run ytm-import --privacy UNLISTED
uv run ytm-import --privacy PUBLIC
```

Use `uv run ytm-import --help` to see options for input, authentication,
`--reauth`, report, and cache paths, as well as the minimum confidence score.

## Import report

After importing, open `import_report.csv` to review skipped matches and errors.
Rows are flushed as the import progresses. `ADDED` means the API confirmed the
addition; `ALREADY_PRESENT` is normal when continuing or repeating an import.

| Status                   | Meaning                                                |
|--------------------------|--------------------------------------------------------|
| `ADDED`                  | The track was successfully added to the playlist.      |
| `ALREADY_PRESENT`        | The track is already in the YouTube Music playlist.    |
| `NOT_FOUND`              | No matching track was found.                           |
| `LOW_CONFIDENCE_SKIPPED` | The match was uncertain and skipped.                   |
| `DUPLICATE_SKIPPED`      | The same track was already selected for this playlist. |
| `ERROR: ...`             | A request failed.                                      |

## Development and tests

Install the locked development dependencies and run the unit suite:

```sh
uv sync --locked
uv run pytest
```

To run a focused part of the suite:

```sh
uv run pytest tests/test_search.py
```

Tests use fake API clients, temporary files, and injected sleep functions. They
require no browser credentials or YouTube Music account and reject real network
requests and sleeps.

The package uses a `src/` layout. `matching.py` contains pure functions;
`match_tracks()` takes a search callable and yields report rows without accessing
files or the API. `SongSearcher` takes a client, cache, and optional sleep
function. Storage helpers take explicit paths. `import_playlists()` takes a
client, input files, an `ImportConfig`, and optional sleep and output functions.
Authentication and command-line parsing belong to `cli.py`.

For example, import orchestration can be called with a fake client:

```python
from pathlib import Path

from ytm_import.config import ImportConfig
from ytm_import.importer import import_playlists

config = ImportConfig(
    report_file=Path("test_report.csv"),
    cache_file=Path("test_cache.json"),
)
import_playlists(
    fake_client,
    [Path("playlists/Jazz.txt")],
    config,
    sleep=lambda seconds: None,
    output=lambda message: None,
)
```

The supplied client implements the five methods in `MusicClient`: `search`,
`get_library_playlists`, `get_playlist`, `create_playlist`, and
`add_playlist_items`. Existing tracks are retrieved with `limit=None`, and
additions use `duplicates=False` as a server-side safeguard. See the
[ytmusicapi playlist reference](https://ytmusicapi.readthedocs.io/en/stable/reference/playlists.html)
for these API options, `tests/conftest.py` for fake client fixtures, and
`tests/test_importer.py` for complete examples, including interruption and lost
response recovery.

## Update dependencies

To update `ytmusicapi` within the project's version requirement:

```sh
uv lock --upgrade-package ytmusicapi
uv sync --locked
```

Review and commit the updated `uv.lock` so everyone uses the same dependency
versions.
