"""OREMO (Unicode edition) launcher.

``oremo --korede`` starts the guide BGM setting tool KOREDE instead (used
by the macOS .app, which contains a single executable).
"""

import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--korede":
        from korede_main import main as korede
        korede()
        return
    from oremo import plat
    from oremo.app import OremoApp
    app = OremoApp(plat.resource_dir(), sys.argv[1:])
    app.run()


if __name__ == "__main__":
    main()
