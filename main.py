"""Default launch opens the local studio. Old workflow: legacy_pipeline.py."""
import sys
from studio.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["serve"]))
