import argparse
import json
import sys
from pathlib import Path

from .core import DEFAULTS, ROOT, load, project_paths, save, validate


def main(argv=None):
    parser=argparse.ArgumentParser(description="Storyforge — free local illustrated-fiction production")
    commands=parser.add_subparsers(dest="command",required=True)
    d=commands.add_parser("doctor",help="Check local services, models, FFmpeg and dependencies");d.add_argument("--project");d.add_argument("--json",action="store_true")
    commands.add_parser("models",help="Download Kokoro/voices from the official ONNX release (about 350 MiB)")
    c=commands.add_parser("create",help="Write and revise a new original story with local Ollama")
    c.add_argument("--topic",required=True);c.add_argument("--seconds",type=int,default=90);c.add_argument("--project",required=True);c.add_argument("--settings",help="JSON settings overrides")
    pilot=commands.add_parser("pilot",help="Create a prepared original pilot project without needing Ollama")
    pilot.add_argument("--project",default="projects/first-film")
    for name in ("run","voice","images","render","package"):
        s=commands.add_parser(name,help="Run/resume "+name+" workflow");s.add_argument("project",help="Path to project.json");s.add_argument("--preview",action="store_true")
    a=commands.add_parser("approve",help="Record a human review of the current final export")
    a.add_argument("project");a.add_argument("--checklist",required=True,help="JSON with five required boolean review confirmations")
    web=commands.add_parser("serve",help="Open the local production dashboard");web.add_argument("--port",type=int,default=8787);web.add_argument("--no-open",action="store_true")
    demo=commands.add_parser("demo",help="Render a short synthetic technical test; NOT a publishable film");demo.add_argument("--directory",default="projects/technical-demo")
    args=parser.parse_args(argv)
    try:
        if args.command=="doctor":
            from .production import doctor
            c=load(args.project).get("settings",{}) if args.project else {};report=doctor(c)
            if args.json:print(json.dumps(report,indent=2))
            else:
                for check in report["checks"]:print(f"{'OK' if check['ok'] else 'MISSING'} / {check['name']}: {check['detail']}")
                print("Ready for automatic production:",report["ready"])
            return 0 if report["ready"] else 2
        if args.command=="models":
            from .production import download_models
            download_models();return 0
        if args.command=="create":
            from .local_ai import create
            folder=Path(args.project).resolve();dest=folder/"project.json"
            if dest.exists():raise ValueError("Project already exists. Choose another directory; existing work is not overwritten.")
            p=create(args.topic,args.seconds,load(args.settings) if args.settings else None);save(dest,p)
            print("Project created:",dest);print("Next: python -m studio run",str(dest));return 0
        if args.command=="pilot":
            from .production import copy_pilot
            dest=copy_pilot(Path(args.project).resolve())
            print("Prepared original pilot:",dest);print("Next: python -m studio run",str(dest));return 0
        if args.command=="serve":
            from .server import serve
            serve(args.port,not args.no_open);return 0
        if args.command=="demo":
            from .demo import demo
            demo(Path(args.directory).resolve());return 0
        folder,p=project_paths(args.project)
        if args.command=="approve":
            from .production import approve
            approve(folder,p,load(args.checklist));print("Review recorded. Nothing has been uploaded or published.")
        else:
            from .production import pipeline
            stages=("voice","images","render","package") if args.command=="run" else (args.command,)
            pipeline(args.project,stages,args.preview)
        return 0
    except KeyboardInterrupt:
        print("Stopped. Completed assets remain cached. Check ComfyUI's queue before resuming.",file=sys.stderr);return 130
    except Exception as exc:
        print(f"Production stopped: {exc}",file=sys.stderr);return 2


if __name__=="__main__":raise SystemExit(main())
