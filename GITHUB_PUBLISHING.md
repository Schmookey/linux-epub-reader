# Working with the GitHub repository

The project is published at https://github.com/Schmookey/linux-epub-reader.

## Clone the repository

    git clone https://github.com/Schmookey/linux-epub-reader.git
    cd linux-epub-reader

## Run and test

    python3 src/linux_epub_reader.py
    python3 -m unittest discover -s tests -v

## Build a Debian package

On Linux Mint or Debian, make sure dpkg-deb, Python 3 and Tkinter are available. Then run:

    bash scripts/build-deb.sh

The generated package is dist/linux-epub-reader_0.13.0-1_all.deb. The dist directory is excluded from Git so generated packages are not accidentally committed.

## Before a public release

Review RELEASE_CHECKLIST.md, test the app on a real Linux Mint desktop and verify the resulting installer on a clean test machine. The current code detects Adobe DRM but does not embed the licensed Adobe DRM engine; do not advertise native in-app Adobe DRM support. ACSM fulfilment is not implemented.

## Licence

The project owner selected CC BY-NC-SA 4.0 for original project materials. Review LICENSE and LICENSE_STATUS.md. Creative Commons advises against using CC licences for software, and the NonCommercial condition can limit catalogue distribution. This project should not be represented as OSI-approved open source.
