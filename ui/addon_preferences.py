from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile

import bpy

from bpy.props import BoolProperty
from bpy.props import IntProperty

from ..core.updater_support import find_addon_root
from ..core.updater_support import is_version_newer
from ..core.updater_support import normalize_version
from ..core.updater_support import parse_version_text
from ..core.updater_support import should_check_for_updates


ADDON_PACKAGE = __package__.split(".")[0]
ADDON_ROOT = Path(__file__).resolve().parent.parent
GITHUB_USER = "wowo-dot"
GITHUB_REPO = "mhw-anim-tools"
REPO_WEBSITE = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}"
RELEASES_WEBSITE = f"{REPO_WEBSITE}/releases"


@dataclass(frozen=True)
class ReleaseInfo:
    version_text: str = ""
    display_name: str = ""
    download_url: str = ""
    html_url: str = ""
    source_kind: str = ""

    @property
    def version_tuple(self) -> tuple[int, int, int] | None:
        return parse_version_text(self.version_text)


class GitHubAddonUpdater:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._current_version = (0, 0, 0)
        self._release_info = ReleaseInfo()
        self._update_ready = False
        self._checking = False
        self._error = ""
        self._last_check = ""
        self._ignored_version = ""
        self._pending_reload = False
        self._installed_version = ""

    @property
    def state_dir(self) -> Path:
        return ADDON_ROOT.parent / f"{ADDON_ROOT.name}_updater"

    @property
    def state_file(self) -> Path:
        return self.state_dir / "state.json"

    @property
    def backup_dir(self) -> Path:
        return self.state_dir / "backups"

    @property
    def release_info(self) -> ReleaseInfo:
        with self._lock:
            return self._release_info

    @property
    def checking(self) -> bool:
        with self._lock:
            return self._checking

    @property
    def update_ready(self) -> bool:
        with self._lock:
            return self._update_ready

    @property
    def error(self) -> str:
        with self._lock:
            return self._error

    @property
    def last_check(self) -> str:
        with self._lock:
            return self._last_check

    @property
    def ignored_version(self) -> str:
        with self._lock:
            return self._ignored_version

    @property
    def pending_reload(self) -> bool:
        with self._lock:
            return self._pending_reload

    def configure(self, *, current_version: tuple[int, ...]) -> None:
        with self._lock:
            self._current_version = normalize_version(current_version)
        self._load_state()
        self._clear_pending_reload_if_reloaded()

    def _default_state(self) -> dict[str, object]:
        return {
            "last_check": "",
            "release_info": {
                "version_text": "",
                "display_name": "",
                "download_url": "",
                "html_url": "",
                "source_kind": "",
            },
            "update_ready": False,
            "error": "",
            "ignored_version": "",
            "pending_reload": False,
            "installed_version": "",
        }

    def _load_state(self) -> None:
        path = self.state_file
        if not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        release_payload = payload.get("release_info") or {}
        with self._lock:
            self._last_check = str(payload.get("last_check") or "")
            self._release_info = ReleaseInfo(
                version_text=str(release_payload.get("version_text") or ""),
                display_name=str(release_payload.get("display_name") or ""),
                download_url=str(release_payload.get("download_url") or ""),
                html_url=str(release_payload.get("html_url") or ""),
                source_kind=str(release_payload.get("source_kind") or ""),
            )
            self._update_ready = bool(payload.get("update_ready"))
            self._error = str(payload.get("error") or "")
            self._ignored_version = str(payload.get("ignored_version") or "")
            self._pending_reload = bool(payload.get("pending_reload"))
            self._installed_version = str(payload.get("installed_version") or "")

    def _save_state(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {
                "last_check": self._last_check,
                "release_info": {
                    "version_text": self._release_info.version_text,
                    "display_name": self._release_info.display_name,
                    "download_url": self._release_info.download_url,
                    "html_url": self._release_info.html_url,
                    "source_kind": self._release_info.source_kind,
                },
                "update_ready": self._update_ready,
                "error": self._error,
                "ignored_version": self._ignored_version,
                "pending_reload": self._pending_reload,
                "installed_version": self._installed_version,
            }
        self.state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _clear_pending_reload_if_reloaded(self) -> None:
        with self._lock:
            installed_version = parse_version_text(self._installed_version)
            if not self._pending_reload or installed_version is None:
                return
            if normalize_version(self._current_version) >= installed_version:
                self._pending_reload = False
                self._installed_version = ""
        self._save_state()

    def _request_json(self, url: str) -> object:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"{ADDON_PACKAGE}-updater",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise RuntimeError(
                    f"GitHub updater metadata was not found for {GITHUB_USER}/{GITHUB_REPO}. "
                    "The repository may still be private, or no public release/tag metadata is available yet."
                ) from exc
            raise RuntimeError(f"GitHub updater request failed with HTTP {exc.code}.") from exc

    def _fetch_latest_release(self) -> ReleaseInfo | None:
        release_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
        try:
            payload = self._request_json(release_url)
        except RuntimeError as exc:
            if "no public release/tag metadata" in str(exc):
                return None
            raise
        if not isinstance(payload, dict):
            return None
        tag_name = str(payload.get("tag_name") or "")
        version = parse_version_text(tag_name)
        if version is None:
            return None
        return ReleaseInfo(
            version_text=tag_name,
            display_name=str(payload.get("name") or tag_name),
            download_url=str(payload.get("zipball_url") or ""),
            html_url=str(payload.get("html_url") or RELEASES_WEBSITE),
            source_kind="release",
        )

    def _fetch_latest_tag(self) -> ReleaseInfo | None:
        tags_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/tags?per_page=20"
        payload = self._request_json(tags_url)
        if not isinstance(payload, list):
            return None
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            version = parse_version_text(name)
            if version is None:
                continue
            return ReleaseInfo(
                version_text=name,
                display_name=name,
                download_url=str(item.get("zipball_url") or f"{REPO_WEBSITE}/archive/refs/tags/{name}.zip"),
                html_url=f"{REPO_WEBSITE}/tree/{name}",
                source_kind="tag",
            )
        return None

    def _fetch_latest_candidate(self) -> ReleaseInfo:
        release = self._fetch_latest_release()
        if release is not None:
            return release
        tag = self._fetch_latest_tag()
        if tag is not None:
            return tag
        raise RuntimeError("No GitHub release or tag could be found for this add-on.")

    def _set_check_result(self, release: ReleaseInfo) -> None:
        now_text = datetime.now().astimezone().isoformat()
        with self._lock:
            self._last_check = now_text
            self._release_info = release
            self._error = ""
            latest_version = release.version_tuple
            ignored = str(self._ignored_version or "")
            self._update_ready = bool(
                latest_version is not None
                and is_version_newer(latest_version, self._current_version)
                and release.version_text != ignored
            )
            self._checking = False
        self._save_state()

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._last_check = datetime.now().astimezone().isoformat()
            self._error = str(message or "Unknown updater error.")
            self._checking = False
            self._update_ready = False
        self._save_state()

    def check_now(self) -> ReleaseInfo:
        with self._lock:
            self._checking = True
            self._error = ""
        try:
            release = self._fetch_latest_candidate()
        except Exception as exc:
            self._set_error(str(exc))
            raise
        self._set_check_result(release)
        return release

    def start_background_check(self, prefs) -> bool:
        interval_ready = should_check_for_updates(
            self.last_check,
            auto_check_enabled=bool(getattr(prefs, "auto_check_update", True)),
            months=int(getattr(prefs, "updater_interval_months", 0)),
            days=int(getattr(prefs, "updater_interval_days", 0)),
            hours=int(getattr(prefs, "updater_interval_hours", 0)),
            minutes=int(getattr(prefs, "updater_interval_minutes", 0)),
        )
        with self._lock:
            if self._checking or not interval_ready:
                return False
            self._checking = True
            self._error = ""

        def _worker() -> None:
            try:
                release = self._fetch_latest_candidate()
            except Exception as exc:
                self._set_error(str(exc))
                return
            self._set_check_result(release)

        thread = threading.Thread(target=_worker, name=f"{ADDON_PACKAGE}-update-check", daemon=True)
        thread.start()
        return True

    def ignore_current_update(self) -> None:
        with self._lock:
            if self._release_info.version_text:
                self._ignored_version = self._release_info.version_text
            self._update_ready = False
        self._save_state()

    def clear_ignored_update(self) -> None:
        with self._lock:
            self._ignored_version = ""
            latest_version = self._release_info.version_tuple
            self._update_ready = bool(
                latest_version is not None
                and is_version_newer(latest_version, self._current_version)
            )
        self._save_state()

    def mark_reload_complete(self) -> None:
        with self._lock:
            self._pending_reload = False
            self._installed_version = ""
        self._save_state()

    def _download_zip(self, url: str, destination: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": f"{ADDON_PACKAGE}-updater"})
        with urllib.request.urlopen(request, timeout=60) as response:
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle)

    def _create_backup(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / timestamp
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            ADDON_ROOT,
            backup_path,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        return backup_path

    def _replace_addon_contents(self, source_root: Path) -> None:
        for child in list(ADDON_ROOT.iterdir()):
            if child.name == ".git":
                raise RuntimeError("Direct in-place updating is disabled for git worktrees.")
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        for child in source_root.iterdir():
            destination = ADDON_ROOT / child.name
            if child.is_dir():
                shutil.copytree(child, destination)
            else:
                shutil.copy2(child, destination)

    def install_update(self) -> str:
        release = self.release_info
        if not release.download_url:
            release = self.check_now()
        if not release.download_url:
            raise RuntimeError("No update payload is available to download.")
        if (ADDON_ROOT / ".git").exists():
            raise RuntimeError("Direct in-place updating is disabled for git worktrees.")

        backup_path = self._create_backup()
        with tempfile.TemporaryDirectory(prefix=f"{ADDON_PACKAGE}_update_") as tmpdir:
            temp_root = Path(tmpdir)
            zip_path = temp_root / "update.zip"
            extract_root = temp_root / "extract"
            extract_root.mkdir(parents=True, exist_ok=True)
            self._download_zip(release.download_url, zip_path)
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(extract_root)
            addon_root = find_addon_root(extract_root)
            if addon_root is None:
                raise RuntimeError("Downloaded update archive did not contain a valid add-on root.")
            self._replace_addon_contents(addon_root)

        with self._lock:
            self._pending_reload = True
            self._installed_version = release.version_text
            self._update_ready = False
            self._ignored_version = ""
            self._error = ""
        self._save_state()
        return str(backup_path)

    def status_text(self) -> str:
        with self._lock:
            if self._pending_reload:
                return "Update installed. Reload scripts or restart Blender."
            if self._checking:
                return "Checking for updates..."
            if self._error:
                if "metadata was not found" in self._error:
                    return "No public GitHub release/tag feed is available yet."
                return f"Update check failed: {self._error}"
            if self._update_ready and self._release_info.version_text:
                return f"Update available: {self._release_info.version_text}"
            if self._last_check:
                return "Addon is up to date."
            return "No update check has run yet."


UPDATER = GitHubAddonUpdater()
_startup_check_registered = False


def get_addon_preferences(context=None):
    ctx = context or bpy.context
    preferences = getattr(ctx, "preferences", None)
    if preferences is None:
        return None
    addon = preferences.addons.get(ADDON_PACKAGE)
    if addon is None:
        return None
    return addon.preferences


class MHWANIMTOOLS_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_PACKAGE

    auto_check_update: BoolProperty(
        name="Auto-check for updates",
        default=True,
        description="Check GitHub for a newer release/tag when Blender starts",
    )
    updater_interval_months: IntProperty(name="Months", default=0, min=0, max=24)
    updater_interval_days: IntProperty(name="Days", default=1, min=0, max=31)
    updater_interval_hours: IntProperty(name="Hours", default=0, min=0, max=23)
    updater_interval_minutes: IntProperty(name="Minutes", default=0, min=0, max=59)

    def draw(self, context):
        layout = self.layout
        layout.label(text="MHW Anim Tools")
        summary = layout.box()
        summary.label(text=f"Installed version: {'.'.join(str(part) for part in normalize_version(UPDATER._current_version))}")
        release = UPDATER.release_info
        if release.version_text:
            summary.label(text=f"Latest found: {release.version_text}")
        summary.label(text=UPDATER.status_text())

        action_row = layout.row(align=True)
        action_row.operator("mhw_anim_tools.check_for_updates", icon="FILE_REFRESH")
        update_button = action_row.operator("mhw_anim_tools.install_update", icon="IMPORT")
        action_row.enabled = not UPDATER.checking
        del update_button

        utility_row = layout.row(align=True)
        utility_row.operator("mhw_anim_tools.clear_ignored_update", icon="LOOP_BACK")
        utility_row.operator("mhw_anim_tools.reload_scripts_after_update", icon="FILE_REFRESH")
        utility_row.operator("wm.url_open", text="Open Releases", icon="URL").url = RELEASES_WEBSITE

        interval_box = layout.box()
        interval_box.label(text="Updater Settings")
        interval_box.prop(self, "auto_check_update")
        interval_row = interval_box.row(align=True)
        interval_row.enabled = self.auto_check_update
        interval_row.prop(self, "updater_interval_months")
        interval_row.prop(self, "updater_interval_days")
        interval_row.prop(self, "updater_interval_hours")
        interval_row.prop(self, "updater_interval_minutes")


class MHWANIMTOOLS_OT_check_for_updates(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.check_for_updates"
    bl_label = "Check for Updates"
    bl_description = "Check GitHub for a newer add-on release"

    def execute(self, context):
        del context
        try:
            release = UPDATER.check_now()
        except Exception as exc:
            self.report({"ERROR"}, f"Update check failed: {exc}")
            return {"CANCELLED"}
        if UPDATER.update_ready:
            self.report({"INFO"}, f"Update available: {release.version_text}")
        else:
            self.report({"INFO"}, "MHW Anim Tools is up to date.")
        return {"FINISHED"}


class MHWANIMTOOLS_OT_install_update(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.install_update"
    bl_label = "Install Update"
    bl_description = "Download and install the latest add-on update from GitHub"

    def execute(self, context):
        del context
        try:
            backup_path = UPDATER.install_update()
        except Exception as exc:
            self.report({"ERROR"}, f"Update install failed: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Update installed. Backup saved to {backup_path}. Reload scripts or restart Blender.")
        return {"FINISHED"}


class MHWANIMTOOLS_OT_clear_ignored_update(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.clear_ignored_update"
    bl_label = "Clear Ignored Update"
    bl_description = "Forget any ignored update version and show it again if still available"

    def execute(self, context):
        del context
        UPDATER.clear_ignored_update()
        self.report({"INFO"}, "Ignored update state cleared.")
        return {"FINISHED"}


class MHWANIMTOOLS_OT_ignore_current_update(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.ignore_current_update"
    bl_label = "Ignore Update"
    bl_description = "Hide the current available update until a newer one appears"

    def execute(self, context):
        del context
        UPDATER.ignore_current_update()
        self.report({"INFO"}, "Current update ignored.")
        return {"FINISHED"}


class MHWANIMTOOLS_OT_reload_scripts_after_update(bpy.types.Operator):
    bl_idname = "mhw_anim_tools.reload_scripts_after_update"
    bl_label = "Reload Scripts"
    bl_description = "Reload Blender scripts after installing an add-on update"

    def execute(self, context):
        del context
        UPDATER.mark_reload_complete()
        bpy.ops.script.reload()
        return {"FINISHED"}


def draw_update_notice_box(layout) -> None:
    if UPDATER.pending_reload:
        box = layout.box()
        box.label(text="Update installed", icon="ERROR")
        box.label(text="Reload scripts or restart Blender to use the new files.")
        row = box.row(align=True)
        row.operator("mhw_anim_tools.reload_scripts_after_update", text="Reload Scripts", icon="FILE_REFRESH")
        row.operator("wm.url_open", text="Open Releases", icon="URL").url = RELEASES_WEBSITE
        return
    if not UPDATER.update_ready:
        return
    release = UPDATER.release_info
    box = layout.box()
    box.label(text=f"Update ready: {release.version_text}", icon="IMPORT")
    if release.display_name and release.display_name != release.version_text:
        box.label(text=release.display_name)
    row = box.row(align=True)
    row.operator("mhw_anim_tools.install_update", text="Install Update", icon="IMPORT")
    row.operator("mhw_anim_tools.ignore_current_update", text="Ignore", icon="X")


def _run_startup_check():
    prefs = get_addon_preferences()
    if prefs is not None:
        UPDATER.start_background_check(prefs)
    return None


classes = (
    MHWANIMTOOLS_AddonPreferences,
    MHWANIMTOOLS_OT_check_for_updates,
    MHWANIMTOOLS_OT_install_update,
    MHWANIMTOOLS_OT_clear_ignored_update,
    MHWANIMTOOLS_OT_ignore_current_update,
    MHWANIMTOOLS_OT_reload_scripts_after_update,
)


def configure(bl_info):
    UPDATER.configure(current_version=tuple(bl_info.get("version", (0, 0, 0))))


def register():
    global _startup_check_registered
    for cls in classes:
        bpy.utils.register_class(cls)
    if not _startup_check_registered:
        bpy.app.timers.register(_run_startup_check, first_interval=2.0)
        _startup_check_registered = True


def unregister():
    global _startup_check_registered
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _startup_check_registered = False
