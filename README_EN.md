# MaxTrack

Free webcam-based head tracking for ETS2 / ATS via OpenTrack UDP.

**Pre-release:** Based on the recovered 0.9.3 source; Windows executable and in-game behavior still require validation.

## Quick start
1. Download the portable Windows build from GitHub Actions artifacts or Releases, and extract the entire archive.
2. Install [OpenTrack](https://github.com/opentrack/opentrack/releases).
3. Configure OpenTrack Input: **UDP over network**, port **4242**; Output: **freetrack 2.0 Enhanced**; click Start.
4. Run MaxTrack.exe, choose your webcam, press F9 to enable, F10 to recenter.

No Python required for portable builds. To develop, install Python 3.11 x64 and run `scripts\run-dev.bat`.

Settings: `%APPDATA%\MaxTrack\config.json`. Webcam video is processed locally.
