"""
NervaOS Feature Pack

Provides deterministic built-in features triggered via slash commands.
These are designed to be reliable and safe, and to work even when LLM
tool-calling is inconsistent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shlex
import subprocess
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List


logger = logging.getLogger("nerva-feature-pack")


class FeaturePack:
    """Collection of built-in slash-command features."""

    def __init__(self, daemon):
        self.daemon = daemon
        self._config_dir = Path.home() / ".config" / "nervaos"
        self._reminders_file = self._config_dir / "reminders.json"

    async def _run(self, cmd: str, timeout: int = 25) -> Tuple[bool, str]:
        return await self.daemon.safety.safe_execute_command(cmd, timeout=timeout)

    def _trim(self, text: str, limit: int = 2500) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "\n... (truncated)"

    async def handle(self, query: str) -> Optional[str]:
        q = query.strip()
        if not q.startswith("/"):
            return None

        parts = q.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        handlers = {
            "/health": self._health,
            "/wifi": self._wifi,
            "/netcheck": self._netcheck,
            "/apps": self._apps,
            "/open": self._open,
            "/find": self._find,
            "/reindex": self._reindex,
            "/processes": self._processes,
            "/disk": self._disk,
            "/startup": self._startup,
            "/logs": self._logs,
            "/services": self._services,
            "/packages": self._packages,
            "/devcheck": self._devcheck,
            "/gitprep": self._gitprep,
            "/repo": self._repo,
            "/cmd": self._cmd_suggest,
            "/term": self._term_exec,
            "/check": self._check_cmd,
            "/explain": self._explain_output,
            "/organize": self._organize,
            "/rename-ext": self._rename_ext,
            "/duplicates": self._duplicates,
            "/docqa": self._docqa,
            "/reminder": self._reminder,
            "/recipe": self._recipe,
            "/fix-connectivity": self._fix_connectivity,
            "/export-diagnostics": self._export_diagnostics,
            "/features": self._features_help,
        }

        handler = handlers.get(cmd)
        if not handler:
            return "Unknown slash command. Try `/features`."
        return await handler(arg)

    async def _features_help(self, _: str) -> str:
        return (
            "Built-in commands:\n"
            "/health, /wifi, /netcheck, /apps, /open <target>, /find <query>, /reindex,\n"
            "/processes, /disk, /startup, /logs,\n"
            "/services, /packages, /devcheck, /gitprep, /repo, /cmd <goal>,\n"
            "/term <command>, /check <command>,\n"
            "/explain <output>, /organize [path], /rename-ext <path> <from> <to>,\n"
            "/duplicates [path], /docqa <question>, /reminder <add|list> ..., /recipe <name>,\n"
            "/fix-connectivity, /export-diagnostics"
        )

    def _desktop_entry_dirs(self) -> List[Path]:
        return [
            Path.home() / ".local" / "share" / "applications",
            Path("/usr/local/share/applications"),
            Path("/usr/share/applications"),
            Path.home() / ".local" / "share" / "flatpak" / "exports" / "share" / "applications",
            Path("/var/lib/flatpak/exports/share/applications"),
        ]

    def _iter_desktop_entries(self):
        for base in self._desktop_entry_dirs():
            if not base.exists():
                continue
            try:
                for p in base.glob("*.desktop"):
                    if p.is_file():
                        yield p
            except OSError:
                continue

    def _parse_desktop_entry(self, path: Path) -> Optional[dict]:
        try:
            name = ""
            exec_line = ""
            no_display = False
            hidden = False
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("Name=") and not name:
                    name = line.split("=", 1)[1].strip()
                elif line.startswith("Exec=") and not exec_line:
                    exec_line = line.split("=", 1)[1].strip()
                elif line.startswith("NoDisplay="):
                    no_display = line.split("=", 1)[1].strip().lower() == "true"
                elif line.startswith("Hidden="):
                    hidden = line.split("=", 1)[1].strip().lower() == "true"
            if hidden:
                return None
            desktop_id = path.name
            if desktop_id.endswith(".desktop"):
                desktop_id = desktop_id[:-8]
            return {
                "name": name or desktop_id,
                "exec": exec_line,
                "desktop_id": desktop_id,
                "no_display": no_display,
                "path": str(path),
            }
        except OSError:
            return None

    def _collect_apps(self, include_hidden: bool = False) -> List[dict]:
        apps = []
        for p in self._iter_desktop_entries():
            item = self._parse_desktop_entry(p)
            if not item:
                continue
            if item["no_display"] and not include_hidden:
                continue
            apps.append(item)
        # De-duplicate by normalized display name
        dedup = {}
        for app in apps:
            key = app["name"].strip().lower()
            if key and key not in dedup:
                dedup[key] = app
        return sorted(dedup.values(), key=lambda x: x["name"].lower())

    def _clean_exec_template(self, exec_line: str) -> str:
        # Remove .desktop placeholders like %f %u %F etc.
        cleaned = re.sub(r"\s+%[fFuUdDnNickvm]", "", exec_line).strip()
        return cleaned

    async def open_target(self, target: str) -> Tuple[bool, str]:
        raw = (target or "").strip()
        if not raw:
            return False, "No target provided."
        if any(x in raw for x in ("|", "&&", "||", ";", "$(", "`")):
            return False, "Blocked: shell operators are not allowed in /open."

        low = raw.lower()
        if low.startswith("open "):
            raw = raw[5:].strip()
            low = raw.lower()
        elif low.startswith("launch "):
            raw = raw[7:].strip()
            low = raw.lower()
        elif low.startswith("start "):
            raw = raw[6:].strip()
            low = raw.lower()
        elif low.startswith("run "):
            raw = raw[4:].strip()
            low = raw.lower()

        # URL
        if low.startswith(("http://", "https://", "file://")) or low.startswith("www."):
            url = raw if "://" in raw else f"https://{raw}"
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True, f"Opened `{url}`"

        # Direct path
        path = Path(raw).expanduser()
        if path.exists():
            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True, f"Opened `{path}`"

        # If it looks like a full command, run directly (no shell).
        if any(raw.startswith(prefix) for prefix in ("xdg-open ", "gio open ", "gtk-launch ")):
            argv = shlex.split(raw)
            subprocess.Popen(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True, f"Launched `{raw}`"

        # Executable in PATH (single binary name only; no arbitrary command args)
        if " " not in raw:
            direct_exe = shutil_which(raw)
        else:
            direct_exe = None
        if direct_exe:
            subprocess.Popen(
                [raw],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True, f"Launched `{raw}`"

        # Match desktop apps by name and launch via gtk-launch.
        apps = self._collect_apps()
        q = low.strip()
        exact = next((a for a in apps if a["name"].strip().lower() == q), None)
        starts = next((a for a in apps if a["name"].strip().lower().startswith(q)), None)
        partial = next((a for a in apps if q in a["name"].strip().lower()), None)
        picked = exact or starts or partial
        if picked:
            if shutil_which("gtk-launch"):
                subprocess.Popen(
                    ["gtk-launch", picked["desktop_id"]],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True, f"Launched `{picked['name']}`"

            exec_line = self._clean_exec_template(picked.get("exec", ""))
            if exec_line:
                argv = shlex.split(exec_line)
                if argv and shutil_which(argv[0]):
                    subprocess.Popen(
                        argv,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    return True, f"Launched `{picked['name']}`"

        return False, f"Could not find app/path/url: `{target}`"

    async def _apps(self, arg: str) -> str:
        query = arg.strip().lower()
        apps = self._collect_apps()
        if query:
            apps = [a for a in apps if query in a["name"].lower()]
        if not apps:
            return "No launchable apps found."
        lines = [f"Launchable apps ({len(apps)} found):"]
        for app in apps[:80]:
            lines.append(f"- {app['name']}")
        if len(apps) > 80:
            lines.append(f"... and {len(apps) - 80} more")
        lines.append("Tip: use `/open <app name>`")
        return "\n".join(lines)

    async def _open(self, arg: str) -> str:
        if not arg:
            return "Usage: /open <app name | file path | folder path | url>"
        try:
            ok, msg = await self.open_target(arg)
            if ok:
                return f"✅ {msg}"
            return f"❌ {msg}"
        except Exception as e:
            return f"❌ Open failed: {e}"

    async def _find(self, arg: str) -> str:
        query = arg.strip()
        if not query:
            return "Usage: /find <name or keyword>"

        lines = []

        # Fast indexed smart search first
        if self.daemon.smart_search:
            try:
                snippet_hits = self.daemon.smart_search.search_with_snippets(query, max_results=8)
                if snippet_hits:
                    lines.append(f"Content matches ({len(snippet_hits)}):")
                    for h in snippet_hits:
                        lines.append(f"- {h['path']}")
                        lines.append(f"  ↳ \"{h['snippet']}\"")
                else:
                    indexed = await self.daemon.smart_search.smart_search(query, max_results=10)
                    if indexed:
                        lines.append(f"Indexed matches ({len(indexed)}):")
                        for r in indexed[:10]:
                            lines.append(f"- {r.path}")
            except Exception as e:
                lines.append(f"Indexed search error: {e}")

        # Fallback filename scan in home dir
        safe_q = shlex.quote(f"*{query}*")
        cmd = f"find {shlex.quote(str(Path.home()))} -iname {safe_q} 2>/dev/null | head -n 30"
        ok, out = await self._run(cmd, timeout=40)
        if ok and out.strip():
            lines.append("\nName matches:")
            lines.extend(f"- {p}" for p in out.splitlines() if p.strip())

        if not lines:
            return f"No files/apps found for `{query}`."
        lines.append("\nTip: use `/open <path or app>` to open a result.")
        return "\n".join(lines)

    async def _reindex(self, _: str) -> str:
        if not self.daemon.smart_search:
            return "Smart search is not available."
        loop = asyncio.get_event_loop()
        try:
            count = await loop.run_in_executor(None, self.daemon.smart_search.index_directories)
            return f"✅ Reindex complete. Updated {count} files with lightweight content indexing."
        except Exception as e:
            return f"❌ Reindex failed: {e}"

    async def _health(self, _: str) -> str:
        out = []
        for c in ("uname -a", "uptime", "free -h", "df -h /"):
            ok, val = await self._run(c)
            out.append(f"$ {c}\n{val if ok else 'error: ' + val}\n")
        return "System Health Report\n\n" + "\n".join(out)

    async def _wifi(self, _: str) -> str:
        ok, ssid = await self._run("nmcli -t -f active,ssid dev wifi")
        if ok:
            active = [line for line in ssid.splitlines() if line.startswith("yes:")]
            if active:
                return f"Connected Wi-Fi: `{active[0].split(':', 1)[1]}`"
        ok2, alt = await self._run("iwgetid -r")
        if ok2 and alt.strip():
            return f"Connected Wi-Fi: `{alt.strip()}`"
        return f"Could not determine Wi-Fi name.\n{ssid if ok else alt}"

    async def _netcheck(self, _: str) -> str:
        checks = [
            "ip route",
            "resolvectl status",
            "ping -c 2 1.1.1.1",
            "ping -c 2 google.com",
        ]
        lines = []
        for c in checks:
            ok, val = await self._run(c)
            lines.append(f"$ {c}\n{self._trim(val if ok else 'error: ' + val, 900)}\n")
        return "Network Diagnostics\n\n" + "\n".join(lines)

    async def _processes(self, _: str) -> str:
        ok1, cpu = await self._run("ps aux --sort=-%cpu")
        ok2, mem = await self._run("ps aux --sort=-%mem")
        if not ok1 and not ok2:
            return f"Failed to read processes.\nCPU: {cpu}\nMEM: {mem}"
        return (
            "Top CPU Processes\n\n"
            + "\n".join(cpu.splitlines()[:12])
            + "\n\nTop Memory Processes\n\n"
            + "\n".join(mem.splitlines()[:12])
        )

    async def _disk(self, _: str) -> str:
        ok1, df = await self._run("df -h")
        home = str(Path.home())
        ok2, du = await self._run(f"du -h -d 1 {home}")
        return (
            "Disk Usage\n\n"
            + (self._trim(df, 1800) if ok1 else f"df error: {df}")
            + "\n\nHome Directory Breakdown\n\n"
            + (self._trim(du, 1800) if ok2 else f"du error: {du}")
        )

    async def _startup(self, _: str) -> str:
        user_dir = Path.home() / ".config" / "autostart"
        system_dir = Path("/etc/xdg/autostart")
        user_items = sorted([p.name for p in user_dir.glob("*.desktop")]) if user_dir.exists() else []
        sys_items = sorted([p.name for p in system_dir.glob("*.desktop")]) if system_dir.exists() else []
        return (
            "Startup Apps\n\n"
            f"User ({len(user_items)}):\n" + ("\n".join(user_items[:40]) or "(none)")
            + "\n\nSystem ({0}):\n".format(len(sys_items))
            + ("\n".join(sys_items[:60]) or "(none)")
        )

    async def _logs(self, _: str) -> str:
        ok, out = await self._run("journalctl -p err -n 60 --no-pager")
        if not ok:
            return f"Could not read logs: {out}"
        return "Recent Error Logs\n\n" + self._trim(out, 3200)

    async def _services(self, _: str) -> str:
        ok, out = await self._run("systemctl --user --no-pager --type=service --state=running")
        if not ok:
            return f"Could not fetch user services: {out}"
        return "Running User Services\n\n" + self._trim(out, 3200)

    async def _packages(self, _: str) -> str:
        ok, out = await self._run("dpkg -l")
        if not ok:
            return f"Could not fetch package list: {out}"
        lines = out.splitlines()
        return f"Installed packages: {max(len(lines) - 5, 0)}\n\n" + self._trim("\n".join(lines[:140]), 3200)

    async def _devcheck(self, _: str) -> str:
        tools = [
            "python3", "pip", "node", "npm", "git", "docker", "docker-compose",
            "code", "gcc", "make", "go", "rustc", "cargo",
        ]
        found = []
        missing = []
        for t in tools:
            p = shutil_which(t)
            if p:
                found.append(f"{t}: {p}")
            else:
                missing.append(t)
        return "Dev Environment Check\n\nFound:\n" + ("\n".join(found) or "(none)") + "\n\nMissing:\n" + (", ".join(missing) or "(none)")

    async def _gitprep(self, _: str) -> str:
        if not self.daemon.code_assistant:
            return "Code assistant not available."
        status = self.daemon.code_assistant.get_git_status()
        commits = self.daemon.code_assistant.get_git_log(n=5)
        if not status:
            return "Not a git repository in current context."
        msg = [f"Branch: {status.branch}", f"Ahead/Behind: {status.ahead}/{status.behind}"]
        msg.append(f"Staged: {len(status.staged)} | Modified: {len(status.unstaged)} | Untracked: {len(status.untracked)}")
        msg.append("\nRecent commits:")
        for c in commits[:5]:
            msg.append(f"- {c['hash']} {c['message']} ({c['author']})")
        return "\n".join(msg)

    async def _repo(self, _: str) -> str:
        if not self.daemon.code_assistant:
            return "Code assistant not available."
        project = self.daemon.code_assistant.detect_project()
        if not project:
            return "Could not detect project info."
        ok, files = await self._run("find . -maxdepth 3 -type f")
        return (
            f"Project: {project.name}\nLanguage: {project.language}\nFramework: {project.framework or 'N/A'}\n"
            f"Path: {project.path}\nFiles: {project.files_count}\n\nSample tree:\n"
            + (self._trim(files, 1800) if ok else files)
        )

    async def _cmd_suggest(self, arg: str) -> str:
        if not arg:
            return "Usage: /cmd <goal>"
        goal = arg.lower()
        templates = {
            "wifi": "nmcli -t -f active,ssid dev wifi",
            "disk": "df -h && du -h -d 1 ~",
            "memory": "free -h",
            "cpu": "ps aux --sort=-%cpu | head -10",
            "logs": "journalctl -p err -n 50 --no-pager",
            "ports": "ss -tulpn",
            "docker": "docker ps -a",
            "git": "git status && git log --oneline -5",
        }
        for k, v in templates.items():
            if k in goal:
                return f"Suggested command for '{arg}':\n`{v}`"
        return "No direct template found. Describe a goal like wifi/disk/cpu/logs/docker/git."

    async def _check_cmd(self, arg: str) -> str:
        if not arg:
            return "Usage: /check <command>"
        ok, reason = self.daemon.safety.is_command_safe(arg)
        return f"{'ALLOWED' if ok else 'BLOCKED'}: {reason}"

    async def _term_exec(self, arg: str) -> str:
        """
        Direct terminal execution from chat.
        Honors safety policy (safe/balanced/power) via SafetyManager.
        """
        if not arg:
            return "Usage: /term <command>\nExample: /term nmcli -t -f active,ssid dev wifi"
        ok, output = await self._run(arg, timeout=45)
        header = f"$ {arg}\n"
        if ok:
            return header + self._trim(output or "(no output)", 3800)
        return header + f"ERROR:\n{self._trim(output, 3800)}"

    async def _explain_output(self, arg: str) -> str:
        if not arg:
            return "Usage: /explain <command output or error text>"
        if self.daemon.ai_client and self.daemon.ai_client.is_available():
            context = await self.daemon.context.get_current_context()
            prompt = (
                "Explain this command output in simple practical terms. "
                "Give likely cause and next safe step.\n\n"
                + arg
            )
            return await self.daemon.ai_client.ask(prompt, context)
        return "AI is not configured. Please set API key in Settings."

    async def _organize(self, arg: str) -> str:
        target = Path(arg).expanduser() if arg else (Path.home() / "Downloads")
        if not target.exists() or not target.is_dir():
            return f"Directory not found: {target}"
        categories = {
            "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"},
            "Documents": {".pdf", ".doc", ".docx", ".txt", ".odt", ".xls", ".xlsx", ".pptx"},
            "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"},
            "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg"},
            "Archives": {".zip", ".tar", ".gz", ".rar", ".7z"},
            "Code": {".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".go", ".rs"},
        }
        moved = 0
        for f in target.iterdir():
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            for cat, exts in categories.items():
                if ext in exts:
                    cat_dir = target / cat
                    cat_dir.mkdir(exist_ok=True)
                    try:
                        f.rename(cat_dir / f.name)
                        moved += 1
                    except OSError:
                        pass
                    break
        return f"Organized files in `{target}`. Moved: {moved}"

    async def _rename_ext(self, arg: str) -> str:
        # /rename-ext <path> <from_ext> <to_ext>
        tokens = arg.split()
        if len(tokens) != 3:
            return "Usage: /rename-ext <path> <from_ext> <to_ext>  (example: /rename-ext ~/Downloads .txt .md)"
        base = Path(tokens[0]).expanduser()
        from_ext = tokens[1]
        to_ext = tokens[2]
        if not base.exists() or not base.is_dir():
            return f"Directory not found: {base}"
        count = 0
        for p in base.iterdir():
            if p.is_file() and p.suffix == from_ext:
                new_name = p.with_suffix(to_ext)
                try:
                    p.rename(new_name)
                    count += 1
                except OSError:
                    pass
        return f"Renamed {count} files from `{from_ext}` to `{to_ext}` in `{base}`."

    async def _duplicates(self, arg: str) -> str:
        root = Path(arg).expanduser() if arg else (Path.home() / "Downloads")
        if not root.exists() or not root.is_dir():
            return f"Directory not found: {root}"
        hashes = {}
        dupes = []
        checked = 0
        for p in root.rglob("*"):
            if checked >= 2500:
                break
            if not p.is_file():
                continue
            checked += 1
            try:
                if p.stat().st_size > 50 * 1024 * 1024:
                    continue
                h = file_hash(p)
            except OSError:
                continue
            prev = hashes.get(h)
            if prev:
                dupes.append((prev, p))
            else:
                hashes[h] = p
        if not dupes:
            return f"No duplicates found in {root} (checked {checked} files)."
        lines = [f"Found {len(dupes)} duplicate pairs (checked {checked} files):"]
        for a, b in dupes[:25]:
            lines.append(f"- {a}\n  {b}")
        if len(dupes) > 25:
            lines.append(f"... and {len(dupes) - 25} more pairs")
        return "\n".join(lines)

    async def _docqa(self, arg: str) -> str:
        if not arg:
            return "Usage: /docqa <question>"
        if self.daemon.smart_search:
            try:
                results = await self.daemon.smart_search.smart_search(arg, max_results=5)
                if not results:
                    return "No relevant docs/files found."
                lines = ["Relevant files:"]
                for r in results:
                    lines.append(f"- {r.filename}: {r.path}")
                if self.daemon.ai_client and self.daemon.ai_client.is_available():
                    context = await self.daemon.context.get_current_context()
                    prompt = "Answer briefly based on likely local docs. Query: " + arg + "\n" + "\n".join(lines)
                    ans = await self.daemon.ai_client.ask(prompt, context)
                    return ans + "\n\n" + "\n".join(lines)
                return "\n".join(lines)
            except Exception as e:
                return f"Doc QA failed: {e}"
        return "Smart search engine is not available."

    async def _reminder(self, arg: str) -> str:
        # /reminder add YYYY-MM-DD HH:MM text...
        # /reminder list
        self._config_dir.mkdir(parents=True, exist_ok=True)
        data = []
        if self._reminders_file.exists():
            try:
                data = json.loads(self._reminders_file.read_text())
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []
        if not arg or arg == "list":
            if not data:
                return "No reminders set."
            lines = ["Reminders:"]
            for i, r in enumerate(data[-30:], 1):
                lines.append(f"{i}. {r.get('when')} - {r.get('text')}")
            return "\n".join(lines)
        if arg.startswith("add "):
            payload = arg[4:].strip()
            parts = payload.split(maxsplit=2)
            if len(parts) < 3:
                return "Usage: /reminder add YYYY-MM-DD HH:MM text"
            when = f"{parts[0]} {parts[1]}"
            text = parts[2]
            data.append({"when": when, "text": text, "created_at": datetime.now().isoformat()})
            self._reminders_file.write_text(json.dumps(data, indent=2))
            return f"Reminder added: {when} - {text}"
        return "Usage: /reminder add YYYY-MM-DD HH:MM text  |  /reminder list"

    async def _recipe(self, arg: str) -> str:
        name = arg.strip() or "my_recipe"
        path = Path.home() / ".config" / "nervaos" / "automation" / "workflows.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        snippet = (
            f"\n- name: \"{name}\"\n"
            "  trigger:\n"
            "    type: \"time\"\n"
            "    schedule: \"daily\"\n"
            "    at: \"09:00\"\n"
            "  actions:\n"
            "    - type: \"notify\"\n"
            "      params:\n"
            f"        message: \"Workflow {name} executed\"\n"
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(snippet)
        return f"Recipe added to `{path}` as workflow `{name}`."

    async def _fix_connectivity(self, _: str) -> str:
        steps = [
            ("Check local route", "ip route"),
            ("Check DNS resolver", "resolvectl status"),
            ("Check external reachability", "ping -c 2 1.1.1.1"),
            ("Check DNS hostname reachability", "ping -c 2 google.com"),
        ]
        lines = []
        for title, cmd in steps:
            ok, out = await self._run(cmd)
            lines.append(f"{title}: {'OK' if ok else 'FAIL'}")
            if not ok:
                lines.append(self._trim(out, 400))
        if any("FAIL" in x for x in lines):
            lines.append("\nTry:")
            lines.append("- reconnect Wi-Fi")
            lines.append("- verify DNS server in Network settings")
            lines.append("- run `/netcheck` for full details")
        return "\n".join(lines)

    async def _export_diagnostics(self, _: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path.home() / ".local" / "share" / "nervaos" / "data"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"diagnostics_{ts}.txt"

        sections = []
        for cmd in [
            "uname -a",
            "uptime",
            "free -h",
            "df -h",
            "ip route",
            "nmcli -t -f active,ssid dev wifi",
            "journalctl -p err -n 80 --no-pager",
        ]:
            ok, out = await self._run(cmd)
            sections.append(f"$ {cmd}\n{out if ok else 'ERROR: ' + out}\n")

        out_file.write_text("\n\n".join(sections), encoding="utf-8")
        return f"Diagnostics exported: `{out_file}`"


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def shutil_which(cmd: str) -> Optional[str]:
    for p in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(p) / cmd
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None
