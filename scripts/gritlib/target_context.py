"""Target filter and context projection helpers."""

from gritlib.record_utils import list_merge_unique
from gritlib.target_store import load_targets


def configured_target_filter(cfg):
    return str(cfg.get("_target_id_filter") or "").strip()


def records_for_target(records, target_id):
    if not target_id:
        return list(records or [])
    return [
        rec for rec in records or []
        if isinstance(rec, dict) and str(rec.get("target_id") or "") == target_id
    ]


def target_context_fields(cfg, target_id):
    target_id = str(target_id or "").strip()
    if not target_id:
        return {}
    rec = (load_targets(cfg).get("targets") or {}).get(target_id)
    if not isinstance(rec, dict):
        rec = {}
    aliases = list_merge_unique(rec.get("aliases") or [], cfg.get("_target_alias_filter") or [])
    return {
        "target_id": target_id,
        "target_label": str(cfg.get("_target_label_filter") or rec.get("label") or ""),
        "target_aliases": [
            str(item) for item in aliases
            if str(item or "")
        ],
        "target_identity_source": "operator-selection",
        "target_identity_confidence": "operator-assigned",
    }


def selected_target_context(cfg):
    return target_context_fields(cfg, configured_target_filter(cfg))


def details_with_target(cfg, details=None, target_context=None):
    out = dict(details or {})
    ctx = dict(target_context if target_context is not None else selected_target_context(cfg))
    for key, value in ctx.items():
        if value not in (None, ""):
            out.setdefault(key, value)
    return out
