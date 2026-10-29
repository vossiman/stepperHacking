import argparse
import sys
from pathlib import Path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="stepper-quests", description="Stepper Quests tray app")
    parser.add_argument("--no-ble", action="store_true", help="do not connect to the stepper")
    parser.add_argument("--demo", action="store_true",
                        help="feed a scripted walk instead of BLE (implies --no-ble)")
    parser.add_argument("--demo-seed", type=int, metavar="N",
                        help="if the store is empty, add one finished N-step session dated yesterday")
    parser.add_argument("--quest", type=Path, metavar="PATH", help="quest JSON file")
    parser.add_argument("--idle-timeout", type=float, metavar="SECONDS",
                        help="override the idle timeout that ends a session")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from .app import main as run

    return run(parse_args(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
