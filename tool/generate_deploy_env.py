import re
import pathlib
import argparse
from dotenv.main import DotEnv

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=pathlib.Path, default=".env")
    parser.add_argument("--override-file", type=pathlib.Path, default="deploy/.env.override")
    parser.add_argument("--output-file", type=pathlib.Path, default="deploy/.env")
    args = parser.parse_args()

    if not args.env_file.exists():
        raise FileNotFoundError(f"Environment file not found: {args.env_file}")

    dotenv = DotEnv(args.env_file).dict()
    overrides = DotEnv(args.override_file).dict()

    with open(args.output_file, "w") as f:
        for key, value in dotenv.items():
            if key in overrides:
                value = overrides[key]
            f.write(f"{key}={value}\n")

