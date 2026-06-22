# HuntOverlay entry point.
# Hunt Map Overlay By sKhaled
#
# This app is a click through, always on top overlay that draws POIs
# (points of interest) inside a user defined rectangle on the screen.
#
# The implementation lives in the huntoverlay package. This file is just the
# launcher so the build command and run command stay simple:
#   python main.py
from huntoverlay.overlay import run

if __name__ == "__main__":
    run()
