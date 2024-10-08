import argparse
import runpy

from .tracer import tracer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=str)
    parser.add_argument("-m", action="store_true")
    parser.add_argument("-o", "--output", type=str, default="trace.json")
    args = parser.parse_args()

    if args.m:
        with tracer(args.output):
            runpy.run_module(args.script)
    else:
        with tracer(args.output):
            runpy.run_path(args.script)


if __name__ == "__main__":
    main()
