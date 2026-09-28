"""KOREDE (guide BGM setting file maker) launcher."""

import os
import sys


def main():
    from oremo.korede import Korede
    if getattr(sys, "frozen", False):
        top = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "guideBGM")
    else:
        top = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "res", "guideBGM")
    Korede(top).run()


if __name__ == "__main__":
    main()
