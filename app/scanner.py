import io
import logging
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

import paramiko

from app import scan_state, store, targets as target_registry
from app.parser import parse_xccdf
from app import ssg_resolver

log = logging.getLogger(__name__)

_BIN_DIR = Path("/app/bin")
_DATA_DIR = Path("/data")
_SSH_KEY_PATH = _DATA_DIR / "ssh" / "id_rsa"
_TMP_PREFIX = "_oscap_dashboard_"

_RPM_FAMILY = {"rhel", "almalinux", "rocky", "centos", "centos stream", "ol", "oracle linux", "sles"}

_public_key_str: str = ""


# ---------------------------------------------------------------------------
# SSH key management
# ---------------------------------------------------------------------------

def ensure_ssh_keypair(key_dir: Path) -> tuple[Path, str]:
    key_dir.mkdir(parents=True, exist_ok=True)
    priv = key_dir / "id_rsa"
    pub = key_dir / "id_rsa.pub"
    if not priv.exists():
        key = paramiko.RSAKey.generate(4096)
        key.write_private_key_file(str(priv))
        os.chmod(priv, 0o600)
        pub_str = f"ssh-rsa {key.get_base64()} openscap-dashboard"
        pub.write_text(pub_str)
        log.info("Generated new SSH keypair at %s", priv)
    else:
        key = paramiko.RSAKey.from_private_key_file(str(priv))
        pub_str = f"ssh-rsa {key.get_base64()} openscap-dashboard"
    return priv, pub_str


def init_ssh_keypair() -> str:
    global _public_key_str
    _, _public_key_str = ensure_ssh_keypair(_SSH_KEY_PATH.parent)
    return _public_key_str


def get_public_key() -> str:
    return _public_key_str


# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------

def _connect(target: dict) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = dict(
        hostname=target["host"],
        port=int(target.get("port") or 22),
        username=target["username"],
        timeout=30,
        banner_timeout=30,
    )
    if target.get("auth_type") == "password":
        fernet = target_registry._fernet
        pwd = target_registry.decrypt_password(target["password_enc"], fernet)
        kwargs["password"] = pwd
    else:
        kwargs["pkey"] = paramiko.RSAKey.from_private_key_file(str(_SSH_KEY_PATH))
    client.connect(**kwargs)
    return client


def _exec(client: paramiko.SSHClient, cmd: str, timeout: int = 60) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    rc = stdout.channel.recv_exit_status()
    return rc, stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")


def detect_os(client: paramiko.SSHClient) -> tuple[str, str]:
    rc, out, _ = _exec(client, "cat /etc/os-release")
    os_id, version_id = "", ""
    for line in out.splitlines():
        if line.startswith("ID="):
            os_id = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("VERSION_ID="):
            version_id = line.split("=", 1)[1].strip().strip('"')
    if not os_id:
        raise RuntimeError("Could not detect OS from /etc/os-release")
    return os_id, version_id


def detect_arch(client: paramiko.SSHClient) -> str:
    _, out, _ = _exec(client, "uname -m")
    arch = out.strip()
    if arch not in ("x86_64", "aarch64"):
        raise RuntimeError(f"Architecture not supported: {arch}")
    return arch


# ---------------------------------------------------------------------------
# File transfer helpers
# ---------------------------------------------------------------------------

def _upload_oscap_bundle(sftp: paramiko.SFTPClient, bin_path: Path, lib_dir: Path) -> None:
    """Upload oscap binary + libs to /tmp on target."""
    sftp.put(str(bin_path), f"/tmp/{_TMP_PREFIX}bin")
    sftp.chmod(f"/tmp/{_TMP_PREFIX}bin", 0o755)
    if lib_dir and lib_dir.exists() and any(lib_dir.iterdir()):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for lib in lib_dir.iterdir():
                tar.add(str(lib), arcname=lib.name)
        buf.seek(0)
        sftp.putfo(buf, f"/tmp/{_TMP_PREFIX}libs.tar.gz")


def _upload_xccdf(sftp: paramiko.SFTPClient, xccdf_path: Path) -> None:
    sftp.put(str(xccdf_path), f"/tmp/{_TMP_PREFIX}content.xml")


def _run_scan(client: paramiko.SSHClient, profile: str,
              use_system_oscap: bool, use_system_content: bool,
              has_libs: bool, system_content_path: str) -> None:
    # Determine oscap invocation
    if use_system_oscap:
        oscap_prefix = "oscap"
    else:
        if has_libs:
            extract = (
                f"mkdir -p /tmp/{_TMP_PREFIX}lib && "
                f"tar -xzf /tmp/{_TMP_PREFIX}libs.tar.gz -C /tmp/{_TMP_PREFIX}lib 2>/dev/null; "
            )
            lib_env = f"LD_LIBRARY_PATH=/tmp/{_TMP_PREFIX}lib:$LD_LIBRARY_PATH "
        else:
            extract, lib_env = "", ""
        oscap_prefix = f"{extract}{lib_env}/tmp/{_TMP_PREFIX}bin"

    content_arg = system_content_path if use_system_content else f"/tmp/{_TMP_PREFIX}content.xml"

    cmd = (
        f"{oscap_prefix} xccdf eval "
        f"--profile {profile} "
        f"--results /tmp/{_TMP_PREFIX}result.xml "
        f"{content_arg}"
    )
    log.info("Running scan: %s", cmd[:120])
    rc, stdout, stderr = _exec(client, cmd, timeout=600)
    log.info("oscap exit code: %d", rc)
    if rc not in (0, 2):  # 0=all pass, 2=some rules failed (normal)
        raise RuntimeError(f"oscap exited {rc}: {(stderr or stdout)[:600]}")


def _download_result(sftp: paramiko.SFTPClient) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tmp:
        tmp_path = tmp.name
    try:
        sftp.get(f"/tmp/{_TMP_PREFIX}result.xml", tmp_path)
        return Path(tmp_path).read_bytes()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _cleanup(client: paramiko.SSHClient) -> None:
    _exec(client, f"rm -rf /tmp/{_TMP_PREFIX}*", timeout=15)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_scan_for_target(target_id: str) -> None:
    if scan_state.is_running(target_id):
        log.warning("Scan already running for %s, skipping", target_id)
        return

    target = target_registry.get_target(target_id)
    if target is None:
        log.error("Target %s not found", target_id)
        return

    scan_state.set_running(target_id)
    client: Optional[paramiko.SSHClient] = None

    try:
        log.info("Starting scan for %s@%s:%s", target["username"], target["host"], target.get("port", 22))
        client = _connect(target)

        os_id, version_id = detect_os(client)
        log.info("Detected OS: %s %s", os_id, version_id)
        detect_arch(client)

        profile_raw = target.get("profile") or "cis"
        profile = ssg_resolver.profile_label_to_id(profile_raw)
        log.info("Profile: %s", profile)

        # --- Determine oscap binary strategy ---
        rc_which, which_out, _ = _exec(client, "which oscap 2>/dev/null || command -v oscap 2>/dev/null || echo ''")
        use_system_oscap = bool(which_out.strip())
        log.info("System oscap: %s (%s)", use_system_oscap, which_out.strip())

        bin_path: Optional[Path] = None
        lib_dir: Optional[Path] = None
        if not use_system_oscap:
            fam = os_id.lower()
            if fam in _RPM_FAMILY:
                bin_path = _BIN_DIR / "oscap-rpm-bin"
                lib_dir = _BIN_DIR / "rpm-lib"
            if bin_path is None or not bin_path.exists():
                raise RuntimeError(
                    f"oscap not found on target and no bundled binary for OS '{os_id}'. "
                    f"Install openscap-scanner: sudo dnf install -y openscap-scanner"
                )

        # --- Determine SSG content strategy ---
        try:
            stem = ssg_resolver.resolve_ssg_stem(os_id, version_id)
        except ssg_resolver.UnsupportedOSError:
            stem = None

        use_system_content = False
        system_content_path = ""
        if stem:
            base = "/usr/share/xml/scap/ssg/content"
            for suffix in ("-ds.xml", "-xccdf.xml", "-ds-1.2.xml"):
                candidate = f"{base}/ssg-{stem}{suffix}"
                _, test_out, _ = _exec(client, f"test -f {candidate} && echo yes || echo no")
                if "yes" in test_out:
                    system_content_path = candidate
                    use_system_content = True
                    log.info("System SSG content found: %s", candidate)
                    break

        xccdf_path: Optional[Path] = None
        if not use_system_content:
            xccdf_path = ssg_resolver.resolve(os_id, version_id)
            if xccdf_path is None:
                raise RuntimeError(
                    f"No SSG content found on target or bundled for OS '{os_id}' {version_id}. "
                    f"Install scap-security-guide: sudo dnf install -y scap-security-guide"
                )
            log.info("Using bundled XCCDF: %s", xccdf_path)

        # --- Upload, scan, download ---
        has_libs = (lib_dir is not None and lib_dir.exists() and any(lib_dir.iterdir()))
        with client.open_sftp() as sftp:
            if not use_system_oscap and bin_path:
                _upload_oscap_bundle(sftp, bin_path, lib_dir)
            if not use_system_content and xccdf_path:
                _upload_xccdf(sftp, xccdf_path)
            _run_scan(client, profile, use_system_oscap, use_system_content,
                      has_libs, system_content_path)
            xml_bytes = _download_result(sftp)

        # --- Parse and store ---
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tmp:
            tmp.write(xml_bytes)
            tmp_path = tmp.name
        try:
            report = parse_xccdf(tmp_path, source=f"ssh:{target['host']}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        report_id = store.add(report)
        scan_state.set_success(target_id, report_id)
        target_registry.update_scan_result(
            target_id, "success", report_id=report_id,
            os_id=os_id, os_version=version_id
        )
        log.info("Scan complete for %s — report %s", target["host"], report_id)

    except Exception as exc:
        err = str(exc)
        log.error("Scan failed for target %s: %s", target_id, err, exc_info=True)
        scan_state.set_failed(target_id, err)
        target_registry.update_scan_result(target_id, "failed", error=err)
    finally:
        if client:
            try:
                _cleanup(client)
            except Exception:
                pass
            client.close()
