#!/usr/bin/env python3
"""Sortly CLI for the Windows File Organizer."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from textwrap import dedent
from typing import Any, Iterable

from .core import CATEGORIES, FileOrganizer, OrganizationPlan, Settings, format_human_timestamp
from .smart_presets import apply_preset, preset_names


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_DARK = "\033[40m"

    @staticmethod
    def disable():
        for attr in [
            "RESET",
            "BOLD",
            "DIM",
            "RED",
            "GREEN",
            "YELLOW",
            "BLUE",
            "MAGENTA",
            "CYAN",
            "WHITE",
            "BG_DARK",
        ]:
            setattr(C, attr, "")


if not sys.stdout.isatty():
    C.disable()


BANNER = f"""
{C.CYAN}{C.BOLD}
  ███████╗██╗██╗     ███████╗ ██████╗ ██████╗  ██████╗
  ██╔════╝██║██║     ██╔════╝██╔═══██╗██╔══██╗██╔════╝
  █████╗  ██║██║     █████╗  ██║   ██║██████╔╝██║  ███╗
  ██╔══╝  ██║██║     ██╔══╝  ██║   ██║██╔══██╗██║   ██║
  ██║     ██║███████╗███████╗╚██████╔╝██║  ██║╚██████╔╝
  ╚═╝     ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝

    {C.RESET}{C.DIM}Sortly: Windows File Organizer — CLI Edition{C.RESET}
"""


class HelpFormatter(argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    pass


SETTING_DESCRIPTIONS = {
    "auto_mode": "Execute organize immediately without confirmation.",
    "schedule_enabled": "Enable scheduled organize runs.",
    "schedule_interval_minutes": "Minutes between scheduled runs.",
    "enable_duplicate_detection": "Hash-based duplicate grouping into Duplicates.",
    "protect_recent_files": "Skip files modified recently.",
    "protect_recent_minutes": "Recency window used when recent-file protection is enabled.",
    "monitor_enabled": "Persist monitored folders as an enabled startup profile.",
    "enable_movie_detection": "Legacy smart media toggle kept for compatibility.",
    "enable_smart_media_detection": "Promote videos to Movies/WebSeries when patterns match.",
    "monitored_folders": "Saved folder list for monitor sessions.",
    "custom_rules": "Filename substring rules mapped to categories.",
    "category_folder_map": "Override category destination folder names.",
    "category_conflict_policy": "Per-category conflict handling: rename, skip, replace.",
    "excluded_extensions": "Extensions to ignore entirely.",
    "excluded_folders": "Folder names treated as already-organized destinations.",
    "log_file": "Configured log file name.",
    "history_file": "Configured history file name.",
}


GUIDES = {
    "overview": dedent(
        """
        Sortly CLI guide

        Core flows:
          sortly organize PATH
          sortly monitor PATH1 PATH2 --save
          sortly undo --preview

        Feature areas mirrored from the GUI:
          - Rules: add, remove, list, and test filename classification.
          - Smart presets: inspect or apply preset bundles.
          - Category mapping: redirect a category into a custom folder name.
          - Conflict policy: choose rename, skip, or replace per category.
          - History: inspect recent sessions and moved files.
          - Config: export/import full settings JSON.
          - Settings: read or update raw config keys when you need exact control.
          - Schedule: persist interval settings or run repeated organize cycles.

        Start here:
          sortly help
          sortly guide organize
          sortly guide settings
        """
    ).strip(),
    "organize": dedent(
        """
        Organize guide

        Preview only:
          sortly organize "C:\\Users\\You\\Downloads" --dry-run --details --show-skipped

        Execute immediately:
          sortly organize "C:\\Users\\You\\Downloads" --auto

        Summary-only preview:
          sortly organize "C:\\Users\\You\\Downloads" --no-preview

        Useful flags:
          --details       Show confidence, destination, and decision reasons.
          --show-skipped  Show skipped files and why they were skipped.
          --limit N       Limit how many files are rendered in the preview.
        """
    ).strip(),
    "rules": dedent(
        """
        Rules guide

        List rules:
          sortly rules list

        Add a rule:
          sortly rules add invoice Documents

        Remove a rule:
          sortly rules remove 1

        Test a filename without moving anything:
          sortly rules test "show.s01e01.mkv"

        Rule matching is substring-based and runs before extension-based detection.
        """
    ).strip(),
    "presets": dedent(
        """
        Presets guide

        List presets:
          sortly presets list

        Inspect one preset:
          sortly presets show Developer

        Apply a preset:
          sortly presets apply Developer

        Presets update the same settings used by the GUI.
        """
    ).strip(),
    "history": dedent(
        """
        History guide

        List recent sessions:
          sortly history list

        Inspect one session in detail:
          sortly history show 1

        Preview what undo would restore:
          sortly undo --preview

        Undo the latest session:
          sortly undo --yes
        """
    ).strip(),
    "config": dedent(
        """
        Config guide

        Show active config:
          sortly config show

        Export config:
          sortly config export sortly-config.json

        Import config:
          sortly config import sortly-config.json

        This uses the same JSON format as the GUI import/export buttons.
        """
    ).strip(),
    "settings": dedent(
        """
        Settings guide

        Show all settings:
          sortly settings show

        Read one setting:
          sortly settings get enable_duplicate_detection

        Update a boolean:
          sortly settings set enable_duplicate_detection true

        Update a list using JSON:
          sortly settings set excluded_extensions "[\".tmp\", \".bak\"]"

        Update a dict using JSON:
          sortly settings set category_folder_map "{\"Audio\": \"Media\"}"
        """
    ).strip(),
    "monitor": dedent(
        """
        Monitor guide

        Start monitoring folders now:
          sortly monitor "C:\\Users\\You\\Downloads" "C:\\Users\\You\\Desktop"

        Save them as the persistent monitored set:
          sortly monitor "C:\\Users\\You\\Downloads" --save

        Reuse saved folders later:
          sortly monitor --use-saved

        Monitoring runs until Ctrl+C.
        """
    ).strip(),
    "schedule": dedent(
        """
        Schedule guide

        Inspect schedule settings:
          sortly schedule show

        Save schedule settings:
          sortly schedule set --enabled true --interval 15

        Run repeated organize cycles:
          sortly schedule run "C:\\Users\\You\\Downloads" --interval 15

        One scheduled cycle for testing:
          sortly schedule run "C:\\Users\\You\\Downloads" --interval 15 --iterations 1 --dry-run
        """
    ).strip(),
}


def print_banner():
    print(BANNER)


def hr(char: str = "─", width: int = 72, color: str = C.DIM):
    print(f"{color}{char * width}{C.RESET}")


def success(msg: str):
    print(f"{C.GREEN}  ✓  {msg}{C.RESET}")


def warn(msg: str):
    print(f"{C.YELLOW}  ⚠  {msg}{C.RESET}")


def error(msg: str):
    print(f"{C.RED}  ✗  {msg}{C.RESET}")


def info(msg: str):
    print(f"{C.CYAN}  ℹ  {msg}{C.RESET}")


def dim(msg: str):
    print(f"{C.DIM}     {msg}{C.RESET}")


def die(msg: str, exit_code: int = 1):
    error(msg)
    raise SystemExit(exit_code)


def confirm(prompt: str) -> bool:
    try:
        resp = input(f"\n{C.YELLOW}  ?  {prompt} {C.DIM}[y/N]{C.RESET} ").strip().lower()
        return resp in {"y", "yes"}
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


def dump_json(value: Any):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def print_kv_rows(rows: Iterable[tuple[str, Any]]):
    rows = list(rows)
    if not rows:
        return
    width = max(len(key) for key, _ in rows)
    for key, value in rows:
        print(f"  {C.BOLD}{key:<{width}}{C.RESET}  {format_value(value)}")


def parse_bool(raw: str) -> bool:
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "y", "on", "enabled"}:
        return True
    if value in {"0", "false", "no", "n", "off", "disabled"}:
        return False
    raise ValueError(f"Expected a boolean value, got '{raw}'")


def parse_setting_value(key: str, raw: str) -> Any:
    if key not in Settings.DEFAULT_SETTINGS:
        raise KeyError(key)
    template = Settings.DEFAULT_SETTINGS[key]

    if isinstance(template, bool):
        return parse_bool(raw)
    if isinstance(template, int):
        return int(raw)
    if isinstance(template, list):
        text = str(raw).strip()
        if text.startswith("["):
            value = json.loads(text)
            if not isinstance(value, list):
                raise ValueError("Expected a JSON list.")
            return value
        return [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(template, dict):
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object.")
        return value
    return raw


def refresh_organizer(organizer: FileOrganizer, settings: Settings):
    organizer.settings = settings
    organizer.categorizer.custom_rules = settings.get("custom_rules", [])


def apply_setting_changes(settings: Settings, changes: dict[str, Any], organizer: FileOrganizer | None = None):
    normalized = dict(changes)
    if "enable_smart_media_detection" in normalized:
        normalized["enable_movie_detection"] = bool(normalized["enable_smart_media_detection"])
    elif "enable_movie_detection" in normalized:
        normalized["enable_smart_media_detection"] = bool(normalized["enable_movie_detection"])

    settings._data.update(normalized)
    settings.save()

    if organizer is not None:
        refresh_organizer(organizer, settings)


def validate_category(category: str) -> str:
    if category not in CATEGORIES:
        die(f"Invalid category '{category}'. Choose from: {', '.join(CATEGORIES.keys())}")
    return category


def validate_conflict_policy(policy: str) -> str:
    value = str(policy).strip().lower()
    if value not in {"rename", "skip", "replace"}:
        die("Invalid conflict policy. Choose from: rename, skip, replace")
    return value


def print_plan(
    plan: OrganizationPlan,
    show_files: bool = True,
    show_details: bool = False,
    show_skipped: bool = False,
    limit: int = 50,
):
    hr()
    print(f"\n{C.BOLD}  Organization Preview{C.RESET}")
    print(
        f"{C.DIM}  {plan.total_files} files to organize, "
        f"{len(plan.new_dirs)} new folder(s) to create{C.RESET}\n"
    )

    for category, count in sorted(plan.categories_summary.items(), key=lambda item: (-item[1], item[0])):
        icon = CATEGORIES.get(category, {}).get("icon", "📁")
        bar = "█" * min(count, 30)
        print(f"  {icon}  {C.BOLD}{category:<15}{C.RESET}  {C.CYAN}{bar}{C.RESET}  {count} file(s)")

    if show_files and plan.moves:
        print(f"\n{C.DIM}  {'File':<38} {'→ Category':<16} {'Size':<10} Destination{C.RESET}")
        hr("─", 92)
        for idx, (source, destination, category) in enumerate(plan.moves[: max(1, limit)]):
            detail = plan.move_details[idx] if idx < len(plan.move_details) else {}
            name = os.path.basename(source)[:37]
            size = format_size(source)
            icon = CATEGORIES.get(category, {}).get("icon", "📁")
            print(
                f"  {name:<38} {icon} {category:<14} {size:<10} "
                f"{C.DIM}{os.path.basename(os.path.dirname(destination))}{C.RESET}"
            )
            if show_details:
                confidence = detail.get("confidence", 0)
                reasons = detail.get("reasons", []) or ["No rule matched."]
                print(f"{C.DIM}     confidence: {confidence}% | destination: {destination}{C.RESET}")
                for reason in reasons:
                    print(f"{C.DIM}     - {reason}{C.RESET}")

        if len(plan.moves) > max(1, limit):
            dim(f"... and {len(plan.moves) - max(1, limit)} more file(s)")

    if show_skipped and plan.skipped:
        print(f"\n{C.BOLD}  Skipped Files{C.RESET}")
        hr("─", 92)
        for path, reason in plan.skipped[: max(1, limit)]:
            print(f"  {os.path.basename(path)}")
            print(f"{C.DIM}     - {reason}{C.RESET}")
        if len(plan.skipped) > max(1, limit):
            dim(f"... and {len(plan.skipped) - max(1, limit)} more skipped file(s)")
    elif plan.skipped:
        print(f"\n{C.DIM}  {len(plan.skipped)} file(s) skipped{C.RESET}")

    print()
    hr()


def progress_bar(current: int, total: int, message: str = "", width: int = 40):
    if total == 0:
        return
    pct = current / total
    filled = int(width * pct)
    bar = f"{'█' * filled}{'░' * (width - filled)}"
    short_message = message[:35] + "…" if len(message) > 35 else message
    sys.stdout.write(
        f"\r  {C.CYAN}{bar}{C.RESET}  {pct * 100:5.1f}%  "
        f"{C.DIM}{short_message:<36}{C.RESET}"
    )
    sys.stdout.flush()
    if current >= total:
        print()


def print_undo_preview(session: dict[str, Any], limit: int = 25):
    moves = session.get("moves", [])
    if not moves:
        warn("The last session has no recorded moves.")
        return
    print(f"\n  {C.BOLD}Undo Preview{C.RESET}")
    print(f"  Session:   {format_human_timestamp(session.get('timestamp', ''))}")
    print(f"  Folder:    {session.get('folder', 'unknown')}")
    print(f"  Restores:  {len(moves)} file(s)\n")
    for move in moves[: max(1, limit)]:
        src_name = Path(move.get("source", "")).name
        dst_name = Path(move.get("destination", "")).name
        print(f"  {dst_name} -> {src_name}")
    if len(moves) > max(1, limit):
        dim(f"... and {len(moves) - max(1, limit)} more file(s)")


def print_history_session(session: dict[str, Any], index: int):
    moves = session.get("moves", [])
    print(f"\n  {C.BOLD}History Session #{index}{C.RESET}")
    print(f"  Time:      {format_human_timestamp(session.get('timestamp', ''))}")
    print(f"  Folder:    {session.get('folder', '')}")
    print(f"  Moves:     {len(moves)}\n")
    if not moves:
        warn("No moves recorded in this session.")
        return
    for move in moves:
        src_name = Path(move.get("source", "")).name
        dst_name = Path(move.get("destination", "")).name
        print(f"  {src_name} -> {dst_name}")


def resolve_monitor_folders(args, settings: Settings) -> list[str]:
    folders = list(args.folders or [])
    if args.use_saved:
        folders.extend(settings.get("monitored_folders", []) or [])
    unique = []
    for folder in folders:
        absolute = os.path.abspath(folder)
        if absolute not in unique:
            unique.append(absolute)
    return unique


def cmd_organize(args, settings: Settings, organizer: FileOrganizer):
    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        die(f"Not a valid directory: {folder}")

    print(f"\n  {C.BOLD}Target:{C.RESET} {folder}")
    info("Scanning files…")
    plan, _ = organizer.organize_folder(folder, auto=False)

    if plan.total_files == 0:
        success("Folder is already organized. Nothing to do.")
        if args.show_skipped and plan.skipped:
            print_plan(plan, show_files=False, show_skipped=True, limit=args.limit)
        return

    print_plan(
        plan,
        show_files=not args.no_preview,
        show_details=args.details,
        show_skipped=args.show_skipped,
        limit=args.limit,
    )

    if args.dry_run:
        warn("Dry run: no files were moved.")
        return

    auto = args.auto or settings.get("auto_mode", False)
    if not auto and not confirm(f"Proceed with organizing {plan.total_files} file(s)?"):
        warn("Cancelled.")
        return

    info("Organizing files…")
    organizer.progress_callback = lambda current, total, message: progress_bar(current, total, message)
    records = organizer.execute_plan(plan, folder)
    success(f"Organized {len(records)} file(s) successfully.")
    info("Use 'undo --preview' to inspect the last session or 'undo' to revert it.")


def cmd_monitor(args, settings: Settings, organizer: FileOrganizer):
    folders = resolve_monitor_folders(args, settings)
    if not folders:
        die("No folders provided. Pass folders directly or use --use-saved.")

    invalid = [folder for folder in folders if not os.path.isdir(folder)]
    if invalid:
        die(f"Invalid folder(s): {', '.join(invalid)}")

    if args.save:
        apply_setting_changes(settings, {"monitored_folders": folders, "monitor_enabled": True}, organizer)
    elif args.folders:
        apply_setting_changes(settings, {"monitored_folders": folders}, organizer)

    print(f"\n  {C.BOLD}Monitoring {len(folders)} folder(s){C.RESET}")
    for folder in folders:
        print(f"  {C.CYAN}  →{C.RESET} {folder}")
    print(f"\n  {C.DIM}Press Ctrl+C to stop monitoring…{C.RESET}\n")
    hr()

    def on_file_organized(src: str, dst: str, category: str):
        icon = CATEGORIES.get(category, {}).get("icon", "📁")
        ts = time.strftime("%H:%M:%S")
        print(f"  {C.DIM}[{ts}]{C.RESET} {icon} {C.GREEN}{os.path.basename(src)}{C.RESET}  →  {category}")

    organizer.start_monitoring(folders, callback=on_file_organized)

    def handle_exit(_sig, _frame):
        print(f"\n\n  {C.YELLOW}Stopping monitor…{C.RESET}")
        organizer.stop_monitoring()
        success("Monitor stopped.")
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    while True:
        time.sleep(1)


def cmd_undo(args, _settings: Settings, organizer: FileOrganizer):
    last = organizer.history.peek_last_session()
    if not last:
        warn("No history found. Nothing to undo.")
        return

    if args.preview:
        print_undo_preview(last, limit=args.limit)
        return

    count = len(last.get("moves", []))
    print(f"\n  {C.BOLD}Last Session:{C.RESET}")
    print(f"  Folder:    {last.get('folder', 'unknown')}")
    print(f"  Time:      {format_human_timestamp(last.get('timestamp', ''))}")
    print(f"  Files:     {count} move(s)\n")

    if not args.yes and not confirm(f"Undo {count} file move(s)?"):
        warn("Cancelled.")
        return

    info("Reverting…")
    ok, msg = organizer.undo_last()
    if ok:
        success(msg)
    else:
        error(msg)


def cmd_status(_args, settings: Settings, organizer: FileOrganizer):
    print(f"\n  {C.BOLD}Sortly Status{C.RESET}\n")
    rows = [
        ("Mode", "Auto" if settings.get("auto_mode") else "Preview/Confirm"),
        ("Monitoring active", organizer.is_monitoring),
        ("Saved monitor profile", settings.get("monitor_enabled", False)),
        ("Schedule enabled", settings.get("schedule_enabled", False)),
        ("Schedule interval", f"{settings.get('schedule_interval_minutes', 15)} min"),
        ("Smart media", settings.get("enable_smart_media_detection", True)),
        ("Duplicate detection", settings.get("enable_duplicate_detection", False)),
        ("Protect recent files", settings.get("protect_recent_files", False)),
        ("Protected window", f"{settings.get('protect_recent_minutes', 30)} min"),
        ("History sessions", organizer.history.session_count),
        ("Rules", len(settings.get("custom_rules", []) or [])),
        ("Mappings", len(settings.get("category_folder_map", {}) or {})),
        ("Conflict policies", len(settings.get("category_conflict_policy", {}) or {})),
        ("Settings file", settings.config_path),
    ]
    print_kv_rows(rows)

    folders = settings.get("monitored_folders", []) or []
    if folders:
        print(f"\n  {C.BOLD}Monitored Folders{C.RESET}")
        for folder in folders:
            print(f"  - {folder}")

    last = organizer.history.peek_last_session()
    if last:
        print(f"\n  {C.BOLD}Last Session{C.RESET}")
        print(f"  {format_human_timestamp(last.get('timestamp', ''))} | {last.get('folder', '')} | {len(last.get('moves', []))} move(s)")
    print()


def cmd_rules(args, settings: Settings, organizer: FileOrganizer):
    rules = list(settings.get("custom_rules", []) or [])

    if args.action == "list":
        if not rules:
            info("No custom rules defined.")
            return
        print(f"\n  {C.BOLD}Custom Rules{C.RESET}\n")
        for index, rule in enumerate(rules, start=1):
            print(f"  {index}. {rule.get('pattern', '')} -> {rule.get('category', 'Others')}")
        return

    if args.action == "add":
        category = validate_category(args.category)
        pattern = args.pattern.strip()
        if not pattern:
            die("Pattern cannot be empty.")
        rules.append({"pattern": pattern, "category": category})
        apply_setting_changes(settings, {"custom_rules": rules}, organizer)
        success(f"Rule added: '{pattern}' -> {category}")
        return

    if args.action == "remove":
        idx = args.index - 1
        if idx < 0 or idx >= len(rules):
            die(f"Invalid rule index: {args.index}")
        removed = rules.pop(idx)
        apply_setting_changes(settings, {"custom_rules": rules}, organizer)
        success(f"Removed rule: '{removed.get('pattern', '')}' -> {removed.get('category', 'Others')}")
        return

    if args.action == "test":
        filename = args.filename.strip()
        if not filename:
            die("Filename cannot be empty.")
        base_folder = os.path.abspath(args.folder or os.getcwd())
        fake_path = str(Path(base_folder) / filename)
        decision = organizer.analyze_file(fake_path, sibling_video_paths=[fake_path])
        destination = organizer._destination_folder_name(decision.category)
        print(f"\n  {C.BOLD}Rule Test{C.RESET}\n")
        rows = [
            ("Filename", filename),
            ("Category", decision.category),
            ("Destination folder", destination),
            ("Confidence", f"{decision.confidence}%"),
            ("Matched rule", decision.matched_rule or "none"),
        ]
        print_kv_rows(rows)
        print(f"\n  {C.BOLD}Reasons{C.RESET}")
        for reason in decision.reasons or ["No rule matched."]:
            print(f"  - {reason}")
        return

    raise AssertionError(f"Unhandled rules action: {args.action}")


def cmd_categories(_args):
    print(f"\n  {C.BOLD}Supported Categories{C.RESET}\n")
    for category, info_dict in CATEGORIES.items():
        icon = info_dict.get("icon", "📁")
        exts = info_dict.get("extensions", [])
        ext_text = ", ".join(exts[:8])
        if len(exts) > 8:
            ext_text += f" … +{len(exts) - 8} more"
        print(f"  {icon}  {C.BOLD}{category:<15}{C.RESET}  {C.DIM}{ext_text or 'catch-all'}{C.RESET}")
    print()


def cmd_presets(args, settings: Settings, organizer: FileOrganizer):
    if args.action == "list":
        print(f"\n  {C.BOLD}Smart Presets{C.RESET}\n")
        for name in preset_names():
            print(f"  - {name}")
        return

    if args.action == "show":
        preset = apply_preset(args.name)
        if not preset:
            die(f"Unknown preset: {args.name}")
        print(f"\n  {C.BOLD}Preset: {args.name}{C.RESET}\n")
        dump_json(preset)
        return

    if args.action == "apply":
        preset = apply_preset(args.name)
        if not preset:
            die(f"Unknown preset: {args.name}")
        apply_setting_changes(settings, preset, organizer)
        success(f"Applied smart preset: {args.name}")
        return

    raise AssertionError(f"Unhandled presets action: {args.action}")


def cmd_config(args, settings: Settings, organizer: FileOrganizer):
    if args.action == "show":
        print(f"\n  {C.BOLD}Active Configuration{C.RESET}\n")
        dump_json(settings._data)
        return

    if args.action == "export":
        path = os.path.abspath(args.path)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(settings._data, handle, indent=2)
        success(f"Configuration exported: {path}")
        return

    if args.action == "import":
        path = os.path.abspath(args.path)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            die(f"Could not read configuration: {exc}")
        if not isinstance(data, dict):
            die("Imported configuration must be a JSON object.")
        apply_setting_changes(settings, data, organizer)
        success(f"Configuration imported: {path}")
        return

    raise AssertionError(f"Unhandled config action: {args.action}")


def cmd_history(args, _settings: Settings, organizer: FileOrganizer):
    if args.action == "list":
        sessions = organizer.history.list_sessions(limit=args.limit)
        if not sessions:
            info("No history sessions yet.")
            return
        print(f"\n  {C.BOLD}Recent History{C.RESET}\n")
        for index, session in enumerate(sessions, start=1):
            timestamp = format_human_timestamp(session.get("timestamp", ""))
            folder = str(session.get("folder", ""))
            move_count = len(session.get("moves", []))
            print(f"  {index:>2}. {timestamp} | {move_count:>3} move(s) | {folder}")
        return

    if args.action == "show":
        sessions = organizer.history.list_sessions(limit=max(50, args.index))
        if args.index < 1 or args.index > len(sessions):
            die(f"History session {args.index} not found.")
        print_history_session(sessions[args.index - 1], args.index)
        return

    raise AssertionError(f"Unhandled history action: {args.action}")


def cmd_mappings(args, settings: Settings, organizer: FileOrganizer):
    mapping = dict(settings.get("category_folder_map", {}) or {})

    if args.action == "list":
        if not mapping:
            info("No custom destination mappings configured.")
            return
        print(f"\n  {C.BOLD}Category Folder Mapping{C.RESET}\n")
        for category, folder_name in sorted(mapping.items()):
            print(f"  {category} -> {folder_name}")
        return

    if args.action == "set":
        category = validate_category(args.category)
        folder_name = args.folder_name.strip()
        if not folder_name:
            die("Target folder name cannot be empty.")
        mapping[category] = folder_name
        apply_setting_changes(settings, {"category_folder_map": mapping}, organizer)
        success(f"Destination mapping saved: {category} -> {folder_name}")
        return

    if args.action == "remove":
        category = validate_category(args.category)
        if category not in mapping:
            die(f"No mapping exists for category: {category}")
        del mapping[category]
        apply_setting_changes(settings, {"category_folder_map": mapping}, organizer)
        success(f"Destination mapping removed for: {category}")
        return

    raise AssertionError(f"Unhandled mappings action: {args.action}")


def cmd_conflicts(args, settings: Settings, organizer: FileOrganizer):
    policies = dict(settings.get("category_conflict_policy", {}) or {})

    if args.action == "list":
        if not policies:
            info("No custom conflict policies configured.")
            return
        print(f"\n  {C.BOLD}Conflict Policies{C.RESET}\n")
        for category, policy in sorted(policies.items()):
            print(f"  {category} -> {policy}")
        return

    if args.action == "set":
        category = validate_category(args.category)
        policy = validate_conflict_policy(args.policy)
        policies[category] = policy
        apply_setting_changes(settings, {"category_conflict_policy": policies}, organizer)
        success(f"Conflict policy saved: {category} -> {policy}")
        return

    if args.action == "remove":
        category = validate_category(args.category)
        if category not in policies:
            die(f"No conflict policy exists for category: {category}")
        del policies[category]
        apply_setting_changes(settings, {"category_conflict_policy": policies}, organizer)
        success(f"Conflict policy removed for: {category}")
        return

    raise AssertionError(f"Unhandled conflicts action: {args.action}")


def cmd_settings(args, settings: Settings, organizer: FileOrganizer):
    if args.action == "keys":
        print(f"\n  {C.BOLD}Available Settings Keys{C.RESET}\n")
        for key in Settings.DEFAULT_SETTINGS:
            print(f"  {key:<28} {SETTING_DESCRIPTIONS.get(key, '')}")
        return

    if args.action == "show":
        if args.key:
            if args.key not in settings._data:
                die(f"Unknown setting key: {args.key}")
            value = settings.get(args.key)
            if args.json or isinstance(value, (dict, list)):
                dump_json(value)
            else:
                print(format_value(value))
            return
        if args.json:
            dump_json(settings._data)
            return
        print(f"\n  {C.BOLD}Current Settings{C.RESET}\n")
        print_kv_rows((key, settings.get(key)) for key in Settings.DEFAULT_SETTINGS)
        return

    if args.action == "get":
        if args.key not in settings._data:
            die(f"Unknown setting key: {args.key}")
        value = settings.get(args.key)
        if isinstance(value, (dict, list)):
            dump_json(value)
        else:
            print(format_value(value))
        return

    if args.action == "set":
        try:
            value = parse_setting_value(args.key, args.value)
        except KeyError:
            die(f"Unknown setting key: {args.key}")
        except Exception as exc:
            die(f"Could not parse value for {args.key}: {exc}")
        apply_setting_changes(settings, {args.key: value}, organizer)
        success(f"Updated {args.key}.")
        return

    raise AssertionError(f"Unhandled settings action: {args.action}")


def cmd_schedule(args, settings: Settings, organizer: FileOrganizer):
    if args.action == "show":
        print(f"\n  {C.BOLD}Schedule Settings{C.RESET}\n")
        print_kv_rows(
            [
                ("Enabled", settings.get("schedule_enabled", False)),
                ("Interval", f"{settings.get('schedule_interval_minutes', 15)} min"),
            ]
        )
        return

    if args.action == "set":
        changes: dict[str, Any] = {}
        if args.enabled is not None:
            changes["schedule_enabled"] = parse_bool(args.enabled)
        if args.interval is not None:
            if args.interval < 1:
                die("Interval must be at least 1 minute.")
            changes["schedule_interval_minutes"] = args.interval
        if not changes:
            die("Nothing to update. Provide --enabled and/or --interval.")
        apply_setting_changes(settings, changes, organizer)
        success("Schedule settings updated.")
        return

    if args.action == "run":
        folder = os.path.abspath(args.folder)
        if not os.path.isdir(folder):
            die(f"Not a valid directory: {folder}")

        interval = args.interval or int(settings.get("schedule_interval_minutes", 15))
        if interval < 1:
            die("Interval must be at least 1 minute.")

        if args.save:
            apply_setting_changes(
                settings,
                {"schedule_enabled": True, "schedule_interval_minutes": interval},
                organizer,
            )

        iterations = args.iterations if args.iterations is not None else 0
        cycle = 0
        print(f"\n  {C.BOLD}Scheduled Organizer{C.RESET}")
        print(f"  Folder:    {folder}")
        print(f"  Interval:  {interval} minute(s)")
        print(f"  Mode:      {'dry-run' if args.dry_run else 'execute'}")
        print(f"  Cycles:    {'infinite' if iterations == 0 else iterations}")
        print(f"\n  {C.DIM}Press Ctrl+C to stop scheduled runs…{C.RESET}\n")

        def stop_schedule(_sig, _frame):
            print(f"\n\n  {C.YELLOW}Stopping scheduled runs…{C.RESET}")
            raise SystemExit(0)

        signal.signal(signal.SIGINT, stop_schedule)
        signal.signal(signal.SIGTERM, stop_schedule)

        while iterations == 0 or cycle < iterations:
            cycle += 1
            info(f"Scheduled cycle {cycle} started")
            plan, _ = organizer.organize_folder(folder, auto=False)
            if plan.total_files == 0:
                success("Nothing to organize in this cycle.")
            elif args.dry_run:
                print_plan(
                    plan,
                    show_files=not args.no_preview,
                    show_details=args.details,
                    show_skipped=args.show_skipped,
                    limit=args.limit,
                )
                warn("Dry run cycle: no files were moved.")
            else:
                organizer.progress_callback = lambda current, total, message: progress_bar(current, total, message)
                records = organizer.execute_plan(plan, folder)
                success(f"Cycle {cycle} moved {len(records)} file(s).")

            if iterations and cycle >= iterations:
                break
            time.sleep(interval * 60)
        return

    raise AssertionError(f"Unhandled schedule action: {args.action}")


def cmd_guide(args):
    topic = args.topic or "overview"
    text = GUIDES.get(topic)
    if text is None:
        die(f"Unknown guide topic: {topic}")
    print()
    print(text)
    print()


def cmd_help(args, parser: argparse.ArgumentParser):
    target = getattr(parser, "_command_parsers", {}).get(args.topic) if args.topic else None
    if target is not None:
        target.print_help()
    else:
        parser.print_help()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sortly",
        description="Sortly: Windows File Organizer CLI with full settings, history, presets, and configuration workflows.",
        formatter_class=HelpFormatter,
        epilog=dedent(
            """
            Quick start:
              sortly organize "C:\\Users\\You\\Downloads" --dry-run --details
              sortly rules test "show.s01e01.mkv"
              sortly presets apply Developer
              sortly config export sortly-config.json
              sortly guide overview
            """
        ),
    )

    sub = parser.add_subparsers(dest="command", metavar="command")
    command_parsers: dict[str, argparse.ArgumentParser] = {}

    p_org = sub.add_parser(
        "organize",
        help="Preview or organize a folder now",
        description="Build a plan for one folder and optionally execute it.",
        formatter_class=HelpFormatter,
    )
    p_org.add_argument("folder", help="Path to the folder to organize")
    p_org.add_argument("--auto", action="store_true", help="Skip confirmation and execute immediately")
    p_org.add_argument("--dry-run", action="store_true", help="Preview only, do not move files")
    p_org.add_argument("--no-preview", action="store_true", help="Hide per-file preview and show only summary")
    p_org.add_argument("--details", action="store_true", help="Show destination, confidence, and decision reasons")
    p_org.add_argument("--show-skipped", action="store_true", help="Show skipped files and reasons")
    p_org.add_argument("--limit", type=int, default=50, help="Maximum files to print in preview sections")
    command_parsers["organize"] = p_org

    p_mon = sub.add_parser(
        "monitor",
        help="Monitor folders in real time",
        description="Watch folders for new files and organize them as they appear.",
        formatter_class=HelpFormatter,
    )
    p_mon.add_argument("folders", nargs="*", help="Folders to monitor")
    p_mon.add_argument("--use-saved", action="store_true", help="Include folders saved in monitored_folders")
    p_mon.add_argument("--save", action="store_true", help="Persist the resulting folder list and mark monitoring enabled")
    command_parsers["monitor"] = p_mon

    p_undo = sub.add_parser(
        "undo",
        help="Preview or undo the last organization session",
        formatter_class=HelpFormatter,
    )
    p_undo.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    p_undo.add_argument("--preview", action="store_true", help="Show what would be restored without undoing")
    p_undo.add_argument("--limit", type=int, default=25, help="Maximum moves to show in preview")
    command_parsers["undo"] = p_undo

    p_status = sub.add_parser(
        "status",
        help="Show current configuration and session status",
        formatter_class=HelpFormatter,
    )
    command_parsers["status"] = p_status

    p_categories = sub.add_parser(
        "categories",
        help="List all categories and representative extensions",
        formatter_class=HelpFormatter,
    )
    command_parsers["categories"] = p_categories

    p_rules = sub.add_parser(
        "rules",
        help="Manage or test custom rules",
        formatter_class=HelpFormatter,
    )
    rules_sub = p_rules.add_subparsers(dest="action", metavar="action")
    rules_sub.add_parser("list", help="List custom rules", formatter_class=HelpFormatter)
    p_rules_add = rules_sub.add_parser("add", help="Add a custom rule", formatter_class=HelpFormatter)
    p_rules_add.add_argument("pattern", help="Filename substring to match")
    p_rules_add.add_argument("category", help="Category to assign when matched")
    p_rules_remove = rules_sub.add_parser("remove", help="Remove a rule by index", formatter_class=HelpFormatter)
    p_rules_remove.add_argument("index", type=int, help="Rule index from rules list")
    p_rules_test = rules_sub.add_parser("test", help="Test how a filename would be classified", formatter_class=HelpFormatter)
    p_rules_test.add_argument("filename", help="Filename to test")
    p_rules_test.add_argument("--folder", help="Folder to simulate as the base path")
    command_parsers["rules"] = p_rules

    p_presets = sub.add_parser(
        "presets",
        help="Inspect or apply smart presets",
        formatter_class=HelpFormatter,
    )
    presets_sub = p_presets.add_subparsers(dest="action", metavar="action")
    presets_sub.add_parser("list", help="List available presets", formatter_class=HelpFormatter)
    p_preset_show = presets_sub.add_parser("show", help="Show one preset", formatter_class=HelpFormatter)
    p_preset_show.add_argument("name", help="Preset name")
    p_preset_apply = presets_sub.add_parser("apply", help="Apply one preset", formatter_class=HelpFormatter)
    p_preset_apply.add_argument("name", help="Preset name")
    command_parsers["presets"] = p_presets

    p_config = sub.add_parser(
        "config",
        help="Show, export, or import full configuration",
        formatter_class=HelpFormatter,
    )
    config_sub = p_config.add_subparsers(dest="action", metavar="action")
    config_sub.add_parser("show", help="Print active config JSON", formatter_class=HelpFormatter)
    p_config_export = config_sub.add_parser("export", help="Export config JSON to a file", formatter_class=HelpFormatter)
    p_config_export.add_argument("path", help="Destination JSON path")
    p_config_import = config_sub.add_parser("import", help="Import config JSON from a file", formatter_class=HelpFormatter)
    p_config_import.add_argument("path", help="Source JSON path")
    command_parsers["config"] = p_config

    p_history = sub.add_parser(
        "history",
        help="Inspect recent organization history",
        formatter_class=HelpFormatter,
    )
    history_sub = p_history.add_subparsers(dest="action", metavar="action")
    p_history_list = history_sub.add_parser("list", help="List recent sessions", formatter_class=HelpFormatter)
    p_history_list.add_argument("--limit", type=int, default=10, help="Maximum sessions to show")
    p_history_show = history_sub.add_parser("show", help="Show a specific recent session", formatter_class=HelpFormatter)
    p_history_show.add_argument("index", type=int, help="Newest-first session index from history list")
    command_parsers["history"] = p_history

    p_mappings = sub.add_parser(
        "mappings",
        help="Manage category destination folder mappings",
        formatter_class=HelpFormatter,
    )
    mappings_sub = p_mappings.add_subparsers(dest="action", metavar="action")
    mappings_sub.add_parser("list", help="List category folder mappings", formatter_class=HelpFormatter)
    p_mappings_set = mappings_sub.add_parser("set", help="Set a destination folder mapping", formatter_class=HelpFormatter)
    p_mappings_set.add_argument("category", help="Category name")
    p_mappings_set.add_argument("folder_name", help="Target folder name")
    p_mappings_remove = mappings_sub.add_parser("remove", help="Remove a destination folder mapping", formatter_class=HelpFormatter)
    p_mappings_remove.add_argument("category", help="Category name")
    command_parsers["mappings"] = p_mappings

    p_conflicts = sub.add_parser(
        "conflicts",
        help="Manage per-category conflict policies",
        formatter_class=HelpFormatter,
    )
    conflicts_sub = p_conflicts.add_subparsers(dest="action", metavar="action")
    conflicts_sub.add_parser("list", help="List conflict policies", formatter_class=HelpFormatter)
    p_conflicts_set = conflicts_sub.add_parser("set", help="Set a conflict policy", formatter_class=HelpFormatter)
    p_conflicts_set.add_argument("category", help="Category name")
    p_conflicts_set.add_argument("policy", help="rename, skip, or replace")
    p_conflicts_remove = conflicts_sub.add_parser("remove", help="Remove a conflict policy", formatter_class=HelpFormatter)
    p_conflicts_remove.add_argument("category", help="Category name")
    command_parsers["conflicts"] = p_conflicts

    p_settings = sub.add_parser(
        "settings",
        help="Inspect or update raw settings keys",
        formatter_class=HelpFormatter,
    )
    settings_sub = p_settings.add_subparsers(dest="action", metavar="action")
    settings_sub.add_parser("keys", help="List available setting keys", formatter_class=HelpFormatter)
    p_settings_show = settings_sub.add_parser("show", help="Show all settings or one key", formatter_class=HelpFormatter)
    p_settings_show.add_argument("key", nargs="?", help="Optional single setting key")
    p_settings_show.add_argument("--json", action="store_true", help="Force JSON output")
    p_settings_get = settings_sub.add_parser("get", help="Get one setting key", formatter_class=HelpFormatter)
    p_settings_get.add_argument("key", help="Setting key")
    p_settings_set = settings_sub.add_parser("set", help="Set one setting key", formatter_class=HelpFormatter)
    p_settings_set.add_argument("key", help="Setting key")
    p_settings_set.add_argument("value", help="New value; use JSON for dicts/lists")
    command_parsers["settings"] = p_settings

    p_schedule = sub.add_parser(
        "schedule",
        help="Inspect schedule settings or run repeated organize cycles",
        formatter_class=HelpFormatter,
    )
    schedule_sub = p_schedule.add_subparsers(dest="action", metavar="action")
    schedule_sub.add_parser("show", help="Show schedule settings", formatter_class=HelpFormatter)
    p_schedule_set = schedule_sub.add_parser("set", help="Update schedule settings", formatter_class=HelpFormatter)
    p_schedule_set.add_argument("--enabled", help="true or false")
    p_schedule_set.add_argument("--interval", type=int, help="Minutes between runs")
    p_schedule_run = schedule_sub.add_parser("run", help="Run organize on a fixed interval", formatter_class=HelpFormatter)
    p_schedule_run.add_argument("folder", help="Folder to organize on each cycle")
    p_schedule_run.add_argument("--interval", type=int, help="Override configured interval in minutes")
    p_schedule_run.add_argument("--iterations", type=int, help="Number of cycles to run; omit for infinite")
    p_schedule_run.add_argument("--dry-run", action="store_true", help="Preview each cycle without moving files")
    p_schedule_run.add_argument("--no-preview", action="store_true", help="Hide per-file preview on dry-run cycles")
    p_schedule_run.add_argument("--details", action="store_true", help="Show detailed decision reasons on dry-run cycles")
    p_schedule_run.add_argument("--show-skipped", action="store_true", help="Show skipped files on dry-run cycles")
    p_schedule_run.add_argument("--limit", type=int, default=50, help="Maximum items to print in previews")
    p_schedule_run.add_argument("--save", action="store_true", help="Persist schedule_enabled and the chosen interval")
    command_parsers["schedule"] = p_schedule

    p_guide = sub.add_parser(
        "guide",
        help="Show workflow guides for the CLI",
        formatter_class=HelpFormatter,
    )
    p_guide.add_argument(
        "topic",
        nargs="?",
        choices=sorted(GUIDES.keys()),
        help="Guide topic",
    )
    command_parsers["guide"] = p_guide

    p_help = sub.add_parser(
        "help",
        help="Show main help or help for one command",
        formatter_class=HelpFormatter,
    )
    p_help.add_argument("topic", nargs="?", choices=sorted(command_parsers.keys()), help="Command name")
    command_parsers["help"] = p_help

    parser._command_parsers = command_parsers
    return parser


def ensure_action(args, parser: argparse.ArgumentParser, command_name: str):
    command_parser = parser._command_parsers[command_name]
    if getattr(args, "action", None) is None:
        command_parser.print_help()
        raise SystemExit(0)


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
        ensure_action(args, parser, "rules")
        cmd_rules(args, settings, organizer)
    elif args.command == "presets":
        ensure_action(args, parser, "presets")
        cmd_presets(args, settings, organizer)
    elif args.command == "config":
        ensure_action(args, parser, "config")
        cmd_config(args, settings, organizer)
    elif args.command == "history":
        ensure_action(args, parser, "history")
        cmd_history(args, settings, organizer)
    elif args.command == "mappings":
        ensure_action(args, parser, "mappings")
        cmd_mappings(args, settings, organizer)
    elif args.command == "conflicts":
        ensure_action(args, parser, "conflicts")
        cmd_conflicts(args, settings, organizer)
    elif args.command == "settings":
        ensure_action(args, parser, "settings")
        cmd_settings(args, settings, organizer)
    elif args.command == "schedule":
        ensure_action(args, parser, "schedule")
        cmd_schedule(args, settings, organizer)
    elif args.command == "guide":
        cmd_guide(args)
    elif args.command == "help":
        cmd_help(args, parser)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
