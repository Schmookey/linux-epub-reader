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

The project licence has not yet been selected. Until the owner adds one, please do not assume contributions can be redistributed under a particular licence. The licence must be resolved before external contributions can be merged.
