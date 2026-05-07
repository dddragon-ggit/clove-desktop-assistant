from __future__ import annotations

import sys


def main() -> int:
    try:
        from .app import main as run_app
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            print(
                "PySide6 is not installed. Install the GUI extra first, for example: "
                "D:\\anaconda3\\envs\\app\\python.exe -m pip install -e .[gui]"
            )
            return 1
        raise

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
