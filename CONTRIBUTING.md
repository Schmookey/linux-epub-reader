# Contributing

Thanks for your interest in Linux EPUB Reader.

## Before making a change

1. Open an issue to discuss substantial behaviour changes.
2. Keep the app local-first. Do not add network access, telemetry, automatic book fetching, or software downloads without explicit project-owner approval and clear documentation.
3. Do not attempt to bypass or remove DRM. Protected-book handling must use a properly authorised integration and clearly report external dependencies.
4. Avoid committing commercial books, DRM licence files, personal reading-state data, account identifiers, passwords or private keys.

## Development checks

```bash
python3 -m py_compile src/linux_epub_reader.py
python3 -m unittest discover -s tests -v
./scripts/build-deb.sh
```

Please add or update synthetic tests for parsing and file-detection changes. The tests should not require commercial books or a real DRM licence.

## Licence

Linux EPUB Reader's original project code is distributed under GNU GPL version 3 only (GPL-3.0-only). By submitting a contribution that you have the right to license, you agree that it may be distributed as part of this project under GPL-3.0-only. You retain copyright in your contribution. Please do not submit code or assets that you do not have permission to license under these terms.
