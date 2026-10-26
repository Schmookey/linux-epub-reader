# Working with the GitHub repository

The project source is published at <https://github.com/Schmookey/linux-epub-reader>.

## Clone the repository

```bash
git clone https://github.com/Schmookey/linux-epub-reader.git
cd linux-epub-reader
```

## Run and test

```bash
python3 src/linux_epub_reader.py
python3 -m unittest discover -s tests -v
```

## Build a Debian package

On Linux Mint or Debian, ensure `dpkg-deb`, Python 3 and Tkinter are installed. Then run:

```bash
bash scripts/build-deb.sh
```

The generated package is written to `dist/linux-epub-reader_0.12.1-1_all.deb`. The `dist/` directory is excluded from Git by default, so generated packages are not accidentally committed.

## Before a public release

Review `RELEASE_CHECKLIST.md`, run the test suite on a real Linux Mint desktop, and verify the resulting installer on a clean test machine. The app detects Adobe DRM but does not embed the licensed Adobe DRM engine; do not advertise native in-app Adobe DRM support. ACSM fulfilment is not implemented.

## Licence

The project owner selected CC BY-NC-SA 4.0 for original project materials. Review `LICENSE` and `LICENSE_STATUS.md`. Creative Commons advises against using CC licences for software, and the NonCommercial condition can limit catalogue distribution. This project should not be represented as OSI-approved open source.
