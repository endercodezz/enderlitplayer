"""Entry point for ``python -m enderlitplayer`` and the frozen Windows build."""

from enderlitplayer.app import main

if __name__ == "__main__":
    raise SystemExit(main())
