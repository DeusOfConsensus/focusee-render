"""
focusee_render/cli.py
=====================
Command-line interface. This is what runs when you type `focusee-render`
in your terminal.
"""

import argparse
import os
import sys
import time
from .render import render


def main():
    parser = argparse.ArgumentParser(
        prog="focusee-render",
        description=(
            "Render a FocuSee project into a polished MP4.\n"
            "Run from inside the .focusee project folder, or pass the folder path."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run from inside the project folder:
  cd "My Project.focusee"
  focusee-render

  # Pass the folder path explicitly:
  focusee-render --project "C:/FocuSee/Projects/My Project.focusee"

  # Custom output location:
  focusee-render --output "C:/Videos/my_tutorial.mp4"
        """,
    )

    parser.add_argument(
        "--project", "-p",
        default=None,
        metavar="PATH",
        help=(
            "Path to the .focusee project folder. "
            "Defaults to the current working directory."
        ),
    )

    parser.add_argument(
        "--output", "-o",
        default=None,
        metavar="PATH",
        help=(
            "Where to save the rendered MP4. "
            "Defaults to rendered_output.mp4 inside the project folder."
        ),
    )

    args = parser.parse_args()

    # Resolve project directory
    project_dir = args.project if args.project else os.getcwd()
    project_dir = os.path.abspath(project_dir)

    if not os.path.isdir(project_dir):
        print(f"✗  Project folder not found: {project_dir}", file=sys.stderr)
        sys.exit(1)

    # Quick sanity check
    config_file = os.path.join(project_dir, "configure.focuseeproj")
    if not os.path.exists(config_file):
        print(
            "✗  This does not look like a FocuSee project folder.\n"
            "   Expected to find: configure.focuseeproj\n"
            f"   Looked in: {project_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    print()
    print("╔══════════════════════════════════════════╗")
    print("║          FocuSee Render Engine           ║")
    print("╚══════════════════════════════════════════╝")
    print(f"  Project : {project_dir}")

    t0 = time.time()
    try:
        output_path = render(project_dir, args.output)
    except FileNotFoundError as e:
        print(f"\n✗  Missing files: {e}", file=sys.stderr)
        sys.exit(1)
    except EnvironmentError as e:
        print(f"\n✗  Environment error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n✗  Render failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    total = time.time() - t0
    print(f"  Total time: {total:.1f}s")
    print()


if __name__ == "__main__":
    main()
