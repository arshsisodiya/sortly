#!/usr/bin/env python3
"""
FileOrganizer CLI
Terminal interface for the smart file organizer.

Usage:
  python organizer_cli.py organize <folder> [--auto] [--dry-run]
  python organizer_cli.py monitor <folder> [<folder2> ...]
  python organizer_cli.py undo
  python organizer_cli.py status
  python organizer_cli.py rules list
  python organizer_cli.py rules add <pattern> <category>
  python organizer_cli.py rules remove <index>
"""

import argparse
import os
import sys
import time
import signal
from pathlib import Path

# Allow running from any location
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from organizer_core import (
    FileOrganizer, Settings, CATEGORIES,
    OrganizationPlan, HistoryManager, format_human_timestamp
)

# ─── ANSI Colors ──────────────────────────────────────────────────────────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BG_DARK = "\033[40m"

    @staticmethod
    def disable():
        """Disable colors for non-terminal output."""
        for attr in ["RESET","BOLD","DIM","RED","GREEN","YELLOW","BLUE","MAGENTA","CYAN","WHITE","BG_DARK"]:
            setattr(C, attr, "")


# Disable colors if not a TTY
if not sys.stdout.isatty():
    C.disable()


# ─── Banner ───────────────────────────────────────────────────────────────────

BANNER = f"""
{C.CYAN}{C.BOLD}
  ███████╗██╗██╗     ███████╗ ██████╗ ██████╗  ██████╗
  ██╔════╝██║██║     ██╔════╝██╔═══██╗██╔══██╗██╔════╝
  █████╗  ██║██║     █████╗  ██║   ██║██████╔╝██║  ███╗
  ██╔══╝  ██║██║     ██╔══╝  ██║   ██║██╔══██╗██║   ██║
  ██║     ██║███████╗███████╗╚██████╔╝██║  ██║╚██████╔╝
  ╚═╝     ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝

  {C.RESET}{C.DIM}Smart Automatic File Organizer — CLI Edition{C.RESET}
"""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def print_banner():
    print(BANNER)

def hr(char="─", width=60, color=C.DIM):
    print(f"{color}{char * width}{C.RESET}")

def success(msg): print(f"{C.GREEN}  ✓  {msg}{C.RESET}")
def warn(msg):    print(f"{C.YELLOW}  ⚠  {msg}{C.RESET}")
def error(msg):   print(f"{C.RED}  ✗  {msg}{C.RESET}")
def info(msg):    print(f"{C.CYAN}  ℹ  {msg}{C.RESET}")
def dim(msg):     print(f"{C.DIM}     {msg}{C.RESET}")

def confirm(prompt: str) -> bool:
    try:
        resp = input(f"\n{C.YELLOW}  ?  {prompt} {C.DIM}[y/N]{C.RESET} ").strip().lower()
        return resp in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False

def format_size(path: str) -> str:
    try:
        size = os.path.getsize(path)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    except Exception:
        return "?"

def print_plan(plan: OrganizationPlan, show_files: bool = True):
    """Pretty-print an OrganizationPlan."""
    hr()
    print(f"\n{C.BOLD}  Organization Preview{C.RESET}")
    print(f"{C.DIM}  {plan.total_files} files to organize, {len(plan.new_dirs)} new folder(s) to create{C.RESET}\n")

    # Category summary
    summary = plan.categories_summary
    for cat, count in sorted(summary.items(), key=lambda x: -x[1]):
        icon = CATEGORIES.get(cat, {}).get("icon", "📁")
        bar = "█" * min(count, 30)
        print(f"  {icon}  {C.BOLD}{cat:<15}{C.RESET}  {C.CYAN}{bar}{C.RESET}  {count} file(s)")

    if show_files and plan.moves:
        print(f"\n{C.DIM}  {'File':<45} {'→ Category':<15} {'Size'}{C.RESET}")
        hr("─", 70)
        for source, dest, cat in plan.moves[:50]:  # Show first 50
            name = os.path.basename(source)[:44]
            size = format_size(source)
            icon = CATEGORIES.get(cat, {}).get("icon", "📁")
            print(f"  {name:<45} {icon} {cat:<13}  {C.DIM}{size}{C.RESET}")

        if len(plan.moves) > 50:
            dim(f"... and {len(plan.moves) - 50} more files")

    if plan.skipped:
        print(f"\n{C.DIM}  {len(plan.skipped)} file(s) skipped{C.RESET}")

    print()
    hr()


def progress_bar(current: int, total: int, message: str = "", width: int = 40):
    if total == 0:
        return
    pct = current / total
    filled = int(width * pct)
    bar = f"{'█' * filled}{'░' * (width - filled)}"
    msg_short = message[:35] + "…" if len(message) > 35 else message
    sys.stdout.write(f"\r  {C.CYAN}{bar}{C.RESET}  {pct*100:5.1f}%  {C.DIM}{msg_short:<36}{C.RESET}")
    sys.stdout.flush()
    if current >= total:
        print()


# ─── Commands ─────────────────────────────────────────────────────────────────

def cmd_organize(args, settings: Settings, organizer: FileOrganizer):
    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        error(f"Not a valid directory: {folder}")
        sys.exit(1)

    print(f"\n  {C.BOLD}Target:{C.RESET} {folder}")
    info("Scanning files…")

    plan, _ = organizer.organize_folder(folder, auto=False)

    if plan.total_files == 0:
        success("Folder is already organized! Nothing to do.")
        return

    print_plan(plan, show_files=not args.no_preview)

    if args.dry_run:
        warn("Dry run — no files were moved.")
        return

    auto = args.auto or settings.get("auto_mode", False)
    if not auto:
        if not confirm(f"Proceed with organizing {plan.total_files} file(s)?"):
            warn("Cancelled.")
            return

    info("Organizing files…")
    organizer.progress_callback = lambda c, t, m: progress_bar(c, t, m)
    records = organizer.execute_plan(plan, folder)
    success(f"Organized {len(records)} file(s) successfully!")
    info(f"Use 'undo' to revert this action.")


def cmd_monitor(args, settings: Settings, organizer: FileOrganizer):
    folders = [os.path.abspath(f) for f in args.folders]
    invalid = [f for f in folders if not os.path.isdir(f)]
    if invalid:
        error(f"Invalid folder(s): {', '.join(invalid)}")
        sys.exit(1)

    print(f"\n  {C.BOLD}Monitoring {len(folders)} folder(s){C.RESET}")
    for f in folders:
        print(f"  {C.CYAN}  →{C.RESET} {f}")

    print(f"\n  {C.DIM}Press Ctrl+C to stop monitoring…{C.RESET}\n")
    hr()

    def on_file_organized(src, dst, category):
        icon = CATEGORIES.get(category, {}).get("icon", "📁")
        ts = time.strftime("%H:%M:%S")
        print(f"  {C.DIM}[{ts}]{C.RESET} {icon} {C.GREEN}{os.path.basename(src)}{C.RESET}  →  {category}")

    organizer.start_monitoring(folders, callback=on_file_organized)

    # Save to settings
    settings.set("monitored_folders", folders)

    def handle_exit(sig, frame):
        print(f"\n\n  {C.YELLOW}Stopping monitor…{C.RESET}")
        organizer.stop_monitoring()
        success("Monitor stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    while True:
        time.sleep(1)


def cmd_undo(args, settings: Settings, organizer: FileOrganizer):
    last = organizer.history.peek_last_session()
    if not last:
        warn("No history found. Nothing to undo.")
        return

    count = len(last.get("moves", []))
    folder = last.get("folder", "unknown")
    ts = format_human_timestamp(last.get("timestamp", ""))

    print(f"\n  {C.BOLD}Last Session:{C.RESET}")
    print(f"  Folder:    {folder}")
    print(f"  Time:      {ts}")
    print(f"  Files:     {count} move(s)\n")

    if not args.yes:
        if not confirm(f"Undo {count} file move(s)?"):
            warn("Cancelled.")
            return

    info("Reverting…")
    ok, msg = organizer.undo_last()
    if ok:
        success(msg)
    else:
        error(msg)


def cmd_status(args, settings: Settings, organizer: FileOrganizer):
    print(f"\n  {C.BOLD}FileOrganizer Status{C.RESET}\n")
    print(f"  Mode:        {'🤖 Auto' if settings.get('auto_mode') else '👁  Preview/Confirm'}")
    print(f"  Monitoring:  {'🟢 Active' if organizer.is_monitoring else '🔴 Inactive'}")
    print(f"  Sessions:    {organizer.history.session_count} in history")

    folders = settings.get("monitored_folders", [])
    if folders:
        print(f"\n  {C.BOLD}Monitored Folders:{C.RESET}")
        for f in folders:
            print(f"    → {f}")

    rules = settings.get("custom_rules", [])
    if rules:
        print(f"\n  {C.BOLD}Custom Rules ({len(rules)}):{C.RESET}")
        for i, rule in enumerate(rules):
            print(f"    {i+1}. Pattern '{rule['pattern']}' → {rule['category']}")

    print()


def cmd_rules(args, settings: Settings):
    rules = settings.get("custom_rules", [])

    if args.action == "list":
        if not rules:
            info("No custom rules defined.")
            return
        print(f"\n  {C.BOLD}Custom Rules:{C.RESET}\n")
        for i, rule in enumerate(rules):
            print(f"  {C.CYAN}{i+1}.{C.RESET}  Pattern: {C.BOLD}{rule['pattern']}{C.RESET}  →  {rule['category']}")
        print()

    elif args.action == "add":
        pattern = args.pattern
        category = args.category

        # Validate category
        valid_cats = list(CATEGORIES.keys())
        if category not in valid_cats:
            error(f"Invalid category '{category}'. Choose from: {', '.join(valid_cats)}")
            sys.exit(1)

        rules.append({"pattern": pattern, "category": category})
        settings.set("custom_rules", rules)
        success(f"Rule added: '{pattern}' → {category}")

    elif args.action == "remove":
        idx = args.index - 1
        if idx < 0 or idx >= len(rules):
            error(f"Invalid rule index: {args.index}")
            sys.exit(1)
        removed = rules.pop(idx)
        settings.set("custom_rules", rules)
        success(f"Removed rule: '{removed['pattern']}' → {removed['category']}")


def cmd_categories(args):
    print(f"\n  {C.BOLD}Supported Categories:{C.RESET}\n")
    for cat, info_dict in CATEGORIES.items():
        icon = info_dict.get("icon", "📁")
        exts = info_dict.get("extensions", [])
        ext_str = ", ".join(exts[:8])
        if len(exts) > 8:
            ext_str += f" … +{len(exts)-8} more"
        print(f"  {icon}  {C.BOLD}{cat:<15}{C.RESET}  {C.DIM}{ext_str or 'catch-all'}{C.RESET}")
    print()


# ─── Argument Parser ──────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fileorganizer",
        description="Smart Automatic File Organizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  fileorganizer organize ~/Downloads
  fileorganizer organize ~/Downloads --auto
  fileorganizer organize ~/Downloads --dry-run
  fileorganizer monitor ~/Downloads ~/Desktop
  fileorganizer undo
  fileorganizer rules add "invoice" Documents
  fileorganizer rules list
  fileorganizer categories
        """,
    )

    sub = parser.add_subparsers(dest="command", metavar="command")

    # organize
    p_org = sub.add_parser("organize", help="Organize a folder")
    p_org.add_argument("folder", help="Path to folder to organize")
    p_org.add_argument("--auto", action="store_true", help="Skip confirmation, organize immediately")
    p_org.add_argument("--dry-run", action="store_true", help="Preview only, do not move files")
    p_org.add_argument("--no-preview", action="store_true", help="Skip per-file preview, show summary only")

    # monitor
    p_mon = sub.add_parser("monitor", help="Monitor folders in real time")
    p_mon.add_argument("folders", nargs="+", help="Folders to monitor")

    # undo
    p_undo = sub.add_parser("undo", help="Undo last organization")
    p_undo.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    # status
    sub.add_parser("status", help="Show current configuration and status")

    # categories
    sub.add_parser("categories", help="List all file categories and extensions")

    # rules
    p_rules = sub.add_parser("rules", help="Manage custom organization rules")
    rules_sub = p_rules.add_subparsers(dest="action", metavar="action")
    rules_sub.add_parser("list", help="List all custom rules")
    p_add = rules_sub.add_parser("add", help="Add a new rule")
    p_add.add_argument("pattern", help="Filename pattern to match")
    p_add.add_argument("category", help="Category to assign matched files")
    p_rm = rules_sub.add_parser("remove", help="Remove a rule by index")
    p_rm.add_argument("index", type=int, help="Rule index (from 'rules list')")

    return parser


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    print_banner()

    parser = build_parser()
    args = parser.parse_args()

    settings = Settings()
    organizer = FileOrganizer(settings=settings)

    if args.command == "organize":
        cmd_organize(args, settings, organizer)
    elif args.command == "monitor":
        cmd_monitor(args, settings, organizer)
    elif args.command == "undo":
        cmd_undo(args, settings, organizer)
    elif args.command == "status":
        cmd_status(args, settings, organizer)
    elif args.command == "categories":
        cmd_categories(args)
    elif args.command == "rules":
        if not args.action:
            parser.parse_args(["rules", "--help"])
        else:
            cmd_rules(args, settings)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
