import argparse
import subprocess
import sys

COMMANDS = {
    "params": [sys.executable, "-m", "core.keystore"],
    "test": [sys.executable, "-m", "unittest", "tests.test_all", "-v"],
    "demo": [sys.executable, "-m", "demo.demo_cli"],
    "bench": [sys.executable, "-u", "-m", "bench.run_all"],
    "plots": [sys.executable, "-m", "bench.plots"],
}


def main():
    ap = argparse.ArgumentParser(prog="main.py")
    ap.add_argument("command", choices=[*COMMANDS, "all"])
    ap.add_argument("extra", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    steps = ["test", "demo", "bench", "plots"] if a.command == "all" else [a.command]
    for step in steps:
        cmd = COMMANDS[step] + (a.extra if a.command != "all" else [])
        print(f"\n=== {step} ===", flush=True)
        code = subprocess.call(cmd)
        if code:
            sys.exit(code)


if __name__ == "__main__":
    main()
