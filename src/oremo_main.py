"""OREMO (Unicode edition) launcher."""

import os
import sys


def topdir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "res"))


def main():
    from oremo.app import OremoApp
    app = OremoApp(topdir(), sys.argv[1:])
    app.run()


if __name__ == "__main__":
    main()
