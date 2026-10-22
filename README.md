# Kuru12 Launcher

The executable opens a native desktop window (Tk), not a browser. It includes its own Python/Tk runtime in the release ZIP.

Open Actions → Build Launcher → Run workflow. The Windows runner builds `Kuru12.exe` and publishes the ZIP plus update manifest to Releases.

Players extract the first release and open Kuru12.exe. It checks this repository for newer releases on startup. Saves live under `%LOCALAPPDATA%/HSHO-Launcher/profiles`, outside the update package.

To publish another update, change `launcher/version.json` to a higher numeric version, upload changed source files, and run the workflow again. Use a new version for each release.

This is an experimental community launcher. Multiplayer fixes and Windows packaging still require real-machine testing. This repository contains launcher code and small supplied asset overrides; no full game, Steam tickets, user saves, or credentials should be uploaded.
