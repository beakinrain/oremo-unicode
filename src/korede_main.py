"""KOREDE (guide BGM setting file maker) launcher."""

import os


def main():
    from oremo import plat
    from oremo.korede import Korede
    top = plat.resource_dir()
    Korede(os.path.join(top, "guideBGM"), ini_dir=plat.user_dir(top)).run()


if __name__ == "__main__":
    main()
