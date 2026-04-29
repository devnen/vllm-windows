from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os
import yaml


def _resolve_configs_path() -> Path:
    """Resolve configs.yaml location.

    Search order:
      1. $VLLM_WINDOWS_CONFIGS env var (absolute path).
      2. Sibling configs.yaml next to the launcher folder (portable layout).
      3. Repo-root launcher/configs.yaml when running from a checkout.
    """
    env = os.environ.get("VLLM_WINDOWS_CONFIGS")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent  # launcher/app/
    portable = here.parent / "configs.yaml"  # launcher/configs.yaml
    if portable.exists():
        return portable
    return Path.cwd() / "launcher" / "configs.yaml"


CONFIGS_PATH = _resolve_configs_path()


@dataclass
class WinConfig:
    id: str
    tagline: str
    tier: str
    status: str
    bat: str
    py: str
    gpu: str
    tp: int
    pp: int
    mem_util: float
    ctx: int
    port: int
    mtp_n: int | None = None
    draft_model_n: int | None = None
    decode_tps: float | None = None
    decode_tps_short: float | None = None
    decode_tps_long: float | None = None
    prefill_tps_cold: float | None = None
    power_cap_w: int | None = None
    notes: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class LinuxConfig:
    id: str
    tagline: str
    tier: str
    status: str
    launch_sh: str | None
    yaml_path: str
    gpu: str
    tp: int
    pp: int
    mem_util: float
    ctx: int
    port: int
    kv_dtype: str
    vision_on: bool
    container: str  # "tp2" or "1gpu"
    mtp_n: int | None = None
    draft_model_n: int | None = None
    decode_tps: float | None = None
    decode_tps_short: float | None = None
    decode_tps_long: float | None = None
    prefill_tps_cold: float | None = None
    power_cap_w: int | None = None
    notes: str = ""
    raw: dict = field(default_factory=dict)
    # convenience aliases so ConfigCard can render Linux configs unchanged
    @property
    def bat(self) -> str:
        return self.launch_sh or ""
    @property
    def py(self) -> str:
        return self.yaml_path


@dataclass
class ConfigsBundle:
    shared_defaults: dict[str, Any]
    windows: list[WinConfig]
    mtp_sweep: dict[str, Any]
    compatibility_matrix: list[dict[str, Any]]
    linux_shared_defaults: dict[str, Any]
    linux: list[LinuxConfig]
    linux_docs: list[str]


def _expand_placeholders(obj: Any, env: dict[str, str]) -> Any:
    """Walk a yaml-loaded structure, replace ${KEY} with env[KEY] in strings."""
    if isinstance(obj, str):
        for k, v in env.items():
            obj = obj.replace("${" + k + "}", v)
        return obj
    if isinstance(obj, dict):
        return {k: _expand_placeholders(v, env) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_placeholders(v, env) for v in obj]
    return obj


def _resolve_repo_root() -> Path:
    """The vllm-windows repo root. launcher/app/ sits two levels deep."""
    return Path(__file__).resolve().parent.parent.parent


def _resolve_env() -> dict[str, str]:
    """Build the placeholder lookup table.

    SNAPSHOTS_DIR — repo_root/snapshots, override via $VLLM_WINDOWS_SNAPSHOTS.
    MODEL_DIR     — $VLLM_MODEL_DIR or  repo_root/models/<default>.
    LOG_DIR       — $VLLM_WINDOWS_LOGS or repo_root/logs.
    """
    root = _resolve_repo_root()
    return {
        "SNAPSHOTS_DIR": os.environ.get("VLLM_WINDOWS_SNAPSHOTS", str(root / "snapshots")),
        "MODEL_DIR":     os.environ.get("VLLM_MODEL_DIR",         str(root / "models" / "Qwen3.6-27B-int4-AutoRound")),
        "LOG_DIR":       os.environ.get("VLLM_WINDOWS_LOGS",      str(root / "logs")),
        "REPO_ROOT":     str(root),
    }


def load() -> ConfigsBundle:
    raw = yaml.safe_load(CONFIGS_PATH.read_text(encoding="utf-8"))
    raw = _expand_placeholders(raw, _resolve_env())
    win = raw["windows"]
    cfgs: list[WinConfig] = []
    for c in win["configs"]:
        cfgs.append(WinConfig(
            id=c["id"], tagline=c["tagline"], tier=c["tier"], status=c["status"],
            bat=c["bat"], py=c["py"], gpu=c["gpu"], tp=c["tp"], pp=c["pp"],
            mem_util=c["mem_util"], ctx=c["ctx"], port=c["port"],
            mtp_n=c.get("mtp_n"), draft_model_n=c.get("draft_model_n"),
            decode_tps=c.get("decode_tps"),
            decode_tps_short=c.get("decode_tps_short"),
            decode_tps_long=c.get("decode_tps_long"),
            prefill_tps_cold=c.get("prefill_tps_cold"),
            power_cap_w=c.get("power_cap_w"),
            notes=c.get("notes", "") or "",
            raw=c,
        ))
    lx = raw.get("linux", {}) or {}
    lx_cfgs: list[LinuxConfig] = []
    for c in lx.get("configs", []):
        lx_cfgs.append(LinuxConfig(
            id=c["id"], tagline=c["tagline"], tier=c["tier"], status=c["status"],
            launch_sh=c.get("launch_sh"), yaml_path=c["yaml_path"],
            gpu=c["gpu"], tp=c["tp"], pp=c["pp"], mem_util=c["mem_util"],
            ctx=c["ctx"], port=c["port"], kv_dtype=c["kv_dtype"],
            vision_on=bool(c.get("vision_on", True)),
            container=c.get("container", "tp2" if c["tp"] == 2 else "1gpu"),
            mtp_n=c.get("mtp_n"), draft_model_n=c.get("draft_model_n"),
            decode_tps=c.get("decode_tps"),
            decode_tps_short=c.get("decode_tps_short"),
            decode_tps_long=c.get("decode_tps_long"),
            prefill_tps_cold=c.get("prefill_tps_cold"),
            power_cap_w=c.get("power_cap_w"),
            notes=c.get("notes", "") or "",
            raw=c,
        ))
    return ConfigsBundle(
        shared_defaults=win.get("shared_defaults", {}),
        windows=cfgs,
        mtp_sweep=win.get("mtp_sweep", {}),
        compatibility_matrix=win.get("compatibility_matrix", []),
        linux_shared_defaults=lx.get("shared_defaults", {}),
        linux=lx_cfgs,
        linux_docs=lx.get("docs", []),
    )
