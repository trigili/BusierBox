"""SSH key helpers for grit-console."""

import base64
from pathlib import Path

try:
    import paramiko
    HAVE_PARAMIKO = True
except ImportError:
    paramiko = None
    HAVE_PARAMIKO = False


def load_public_key(path):
    if not HAVE_PARAMIKO:
        return None
    key_path = Path(path).expanduser()
    if not key_path.is_file():
        raise RuntimeError(f"authorized dbclient public key not found: {key_path}")
    text = key_path.read_text(encoding="utf-8").strip()
    parts = text.split()
    if len(parts) < 2:
        raise RuntimeError(f"malformed public key file: {key_path}")
    key_type, key_data = parts[0], parts[1]
    blob = base64.b64decode(key_data.encode("ascii"))
    for cls in (paramiko.RSAKey, paramiko.ECDSAKey, paramiko.Ed25519Key):
        try:
            return cls(data=blob)
        except Exception:
            continue
    raise RuntimeError(f"unsupported public key type '{key_type}': {key_path}")


def keys_equal(a, b):
    """Compare two Paramiko PKey objects by type and base64 content."""
    if a is None or b is None:
        return False
    return a.get_name() == b.get_name() and a.get_base64() == b.get_base64()


def ensure_host_key(path):
    if not HAVE_PARAMIKO:
        return None
    key_path = Path(path).expanduser()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.is_file():
        return paramiko.RSAKey(filename=str(key_path))
    key = paramiko.RSAKey.generate(3072)
    key.write_private_key_file(str(key_path))
    return key
