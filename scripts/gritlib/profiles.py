"""Target profile persistence for grit-console."""

import re
from pathlib import Path

from gritlib.release_artifacts import kernel_floor_from_release, normalized_probe_arch
from gritlib.session_state import atomic_write_json, read_json_file, utc_now


PROFILE_SCHEMA = 1
PROFILE_EDITABLE_KEYS = {
    "name",
    "source",
    "probe_result_id",
    "target_id",
    "target_label",
    "uname_s",
    "uname_m",
    "uname_r",
    "word_bits",
    "endian",
    "arch",
    "kernel_floor",
    "tuple_path",
    "operator_host",
    "preferred_payload_preset",
    "preferred_transport",
    "notes",
}
PROFILE_KEY_HINTS = (
    "target_id", "target_label", "arch", "kernel_floor", "tuple_path",
    "operator_host", "preferred_payload_preset", "preferred_transport", "notes",
)


def profiles_path(cfg):
    configured = str((cfg or {}).get("profiles_file") or "").strip()
    if configured:
        return Path(configured)
    return Path(str((cfg or {}).get("operator_session_dir", "local/operator-session"))) / "profiles.json"


def empty_profiles_doc():
    return {"schema": PROFILE_SCHEMA, "active": "", "profiles": {}}


def load_profiles(cfg):
    data = read_json_file(profiles_path(cfg), empty_profiles_doc())
    if not isinstance(data, dict):
        data = empty_profiles_doc()
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        profiles = {}
    clean = empty_profiles_doc()
    clean["active"] = str(data.get("active") or "")
    clean["profiles"] = {
        str(name): dict(profile)
        for name, profile in profiles.items()
        if isinstance(profile, dict)
    }
    if clean["active"] and clean["active"] not in clean["profiles"]:
        clean["active"] = ""
    return clean


def save_profiles(cfg, data):
    doc = empty_profiles_doc()
    doc.update(data or {})
    if not isinstance(doc.get("profiles"), dict):
        doc["profiles"] = {}
    if doc.get("active") and doc["active"] not in doc["profiles"]:
        doc["active"] = ""
    atomic_write_json(profiles_path(cfg), doc)
    return doc


def profile_records(cfg):
    data = load_profiles(cfg)
    out = []
    for idx, name in enumerate(sorted(data.get("profiles") or {}), 1):
        rec = dict((data.get("profiles") or {}).get(name) or {})
        rec.setdefault("name", name)
        rec["_index"] = idx
        rec["_active"] = name == data.get("active")
        out.append(rec)
    return out


def active_profile(cfg):
    data = load_profiles(cfg)
    name = str(data.get("active") or "")
    if not name:
        return {}
    rec = dict((data.get("profiles") or {}).get(name) or {})
    if rec:
        rec.setdefault("name", name)
    return rec


def resolve_profile_name(cfg, selector):
    text = str(selector or "").strip()
    data = load_profiles(cfg)
    profiles = data.get("profiles") or {}
    if not text:
        return str(data.get("active") or "")
    if text in profiles:
        return text
    slug = profile_slug(text)
    if slug in profiles:
        return slug
    if text.isdigit():
        records = profile_records(cfg)
        idx = int(text) - 1
        if 0 <= idx < len(records):
            return str(records[idx].get("name") or "")
    return ""


def profile_slug(value, fallback="profile"):
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.-]+", "-", text).strip("-._")
    return text or fallback


def create_profile(cfg, name, values=None, make_active=True):
    name = profile_slug(name)
    data = load_profiles(cfg)
    profiles = data.setdefault("profiles", {})
    if name in profiles:
        raise ValueError(f"profile already exists: {name}")
    rec = {
        "name": name,
        "source": "manual",
        "updated_at": utc_now(),
        "preferred_payload_preset": "default",
        "preferred_transport": "ssh",
        "notes": "",
    }
    rec.update(values or {})
    rec["name"] = name
    profiles[name] = rec
    if make_active:
        data["active"] = name
    save_profiles(cfg, data)
    return rec


def set_active_profile(cfg, selector):
    name = resolve_profile_name(cfg, selector)
    if not name:
        raise ValueError(f"profile not found: {selector}")
    data = load_profiles(cfg)
    data["active"] = name
    save_profiles(cfg, data)
    rec = dict((data.get("profiles") or {}).get(name) or {})
    rec.setdefault("name", name)
    return rec


def clear_active_profile(cfg):
    data = load_profiles(cfg)
    data["active"] = ""
    save_profiles(cfg, data)


def delete_profile(cfg, selector):
    name = resolve_profile_name(cfg, selector)
    if not name:
        raise ValueError(f"profile not found: {selector}")
    data = load_profiles(cfg)
    rec = (data.get("profiles") or {}).pop(name, {})
    if data.get("active") == name:
        data["active"] = ""
    save_profiles(cfg, data)
    return rec


def set_profile_value(cfg, key, value):
    key = str(key or "").strip()
    if key not in PROFILE_EDITABLE_KEYS:
        hints = ", ".join(PROFILE_KEY_HINTS)
        raise ValueError(f"unknown profile key: {key}; editable keys include: {hints}")
    data = load_profiles(cfg)
    name = str(data.get("active") or "")
    if not name:
        raise ValueError("no active profile - run: profile create NAME or profile use N")
    rec = dict((data.get("profiles") or {}).get(name) or {})
    if key == "name":
        new_name = profile_slug(value)
        if new_name != name and new_name in data.get("profiles", {}):
            raise ValueError(f"profile already exists: {new_name}")
        rec["name"] = new_name
        data["profiles"].pop(name, None)
        data["profiles"][new_name] = rec
        data["active"] = new_name
    else:
        rec[key] = str(value)
        rec["updated_at"] = utc_now()
        data["profiles"][name] = rec
    save_profiles(cfg, data)
    return rec


def _probe_target_name(rec, ordinal=""):
    for key in ("target_label", "target_id", "hostname", "host", "device"):
        value = str(rec.get(key) or "").strip()
        if value:
            return profile_slug(value)
    uname_m = str(rec.get("uname_m") or rec.get("architecture") or "target")
    suffix = str(rec.get("received_at") or utc_now()).replace(":", "").replace("-", "")[:15]
    ordinal_text = f"-{ordinal}" if ordinal else ""
    return profile_slug(f"probe-{uname_m}{ordinal_text}-{suffix}")


def profile_from_probe_result(rec, ordinal="", existing=None):
    existing = dict(existing or {})
    uname_m = str(rec.get("uname_m") or rec.get("architecture") or "")
    endian = str(rec.get("endian") or "")
    arch = normalized_probe_arch(uname_m, endian)
    kernel = str(rec.get("uname_r") or rec.get("kernel") or "")
    kernel_floor = kernel_floor_from_release(kernel)
    preferred_preset = existing.get("preferred_payload_preset") or "default"
    preferred_transport = existing.get("preferred_transport") or "ssh"
    operator_host = (
        rec.get("operator_host")
        or rec.get("operator_host_used")
        or rec.get("listener_host")
        or rec.get("local_addr")
        or existing.get("operator_host")
        or ""
    )
    tuple_path = existing.get("tuple_path") or ""
    values = {
        "source": "probe",
        "updated_at": utc_now(),
        "probe_result_id": str(ordinal or existing.get("probe_result_id") or ""),
        "target_id": str(rec.get("target_id") or existing.get("target_id") or ""),
        "target_label": str(rec.get("target_label") or existing.get("target_label") or ""),
        "uname_s": str(rec.get("uname_s") or "Linux"),
        "uname_m": uname_m,
        "uname_r": kernel,
        "word_bits": str(rec.get("word_bits") or ""),
        "endian": endian,
        "arch": arch,
        "kernel_floor": kernel_floor,
        "tuple_path": tuple_path,
        "operator_host": str(operator_host),
        "preferred_payload_preset": str(preferred_preset),
        "preferred_transport": str(preferred_transport),
        "notes": str(existing.get("notes") or ""),
    }
    return {key: value for key, value in values.items() if value != ""}


def upsert_profile_from_probe(cfg, rec, ordinal="", selector=""):
    data = load_profiles(cfg)
    profiles = data.setdefault("profiles", {})
    name = resolve_profile_name(cfg, selector) if selector else str(data.get("active") or "")
    created = False
    if not name:
        name = _probe_target_name(rec, ordinal=ordinal)
        base = name
        i = 2
        while name in profiles:
            name = f"{base}-{i}"
            i += 1
        created = True
    existing = dict(profiles.get(name) or {})
    values = profile_from_probe_result(rec, ordinal=ordinal, existing=existing)
    updated = dict(existing)
    updated.update(values)
    updated["name"] = name
    profiles[name] = updated
    data["active"] = name
    save_profiles(cfg, data)
    return updated, created


def profile_release_selector(profile, preset=""):
    profile = profile or {}
    tuple_path = str(profile.get("tuple_path") or "").strip()
    preset = str(preset or profile.get("preferred_payload_preset") or "default").strip()
    if tuple_path and preset:
        return f"by_tuple_payload_preset:{tuple_path}:{preset}"
    if tuple_path:
        return f"by_tuple_path:{tuple_path}"
    return ""


def profile_summary_line(profile):
    if not profile:
        return "none"
    target = " ".join(
        part for part in (
            str(profile.get("arch") or profile.get("uname_m") or ""),
            str(profile.get("uname_s") or ""),
            str(profile.get("uname_r") or ""),
            str(profile.get("endian") or ""),
        )
        if part
    )
    host = str(profile.get("operator_host") or "")
    suffix = f" operator {host}" if host else ""
    return f"{profile.get('name', '-')}: {target or '-'}{suffix}"
