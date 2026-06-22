# HuntOverlay package
# Hunt Map Overlay By sKhaled
#
# A click through, always on top overlay that draws POIs (points of interest)
# inside a user defined rectangle on the screen.
#
# Module overview
#   constants.py  shared constants (map order, config version, virtual key codes)
#   win32.py      Win32 helpers (async key state, topmost, click through)
#   paths.py      runtime paths and JSON file helpers
#   helpers.py    color, screen/aspect, keybind label and data format helpers
#   config.py     default config, rect ratios, keybinds and config load/replace
#   widgets.py    reusable UI widgets and dialogs
#   panel.py      settings Panel window
#   overlay.py    main Overlay window and the run() entry point
