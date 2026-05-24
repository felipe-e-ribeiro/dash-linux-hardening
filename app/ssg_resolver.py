import logging
import xml.etree.ElementTree as ET
from pathlib import Path

log = logging.getLogger(__name__)

# Where bundled SSG files live in the Docker image
BUNDLED_SSG_DIR = Path("/app/ssg-content")

# (os_id.lower(), major_version) -> SSG filename stem (ssg-<stem>-xccdf.xml)
OS_MAP: dict[tuple[str, str], str] = {
    ("rhel", "7"): "rhel7",
    ("rhel", "8"): "rhel8",
    ("rhel", "9"): "rhel9",
    ("almalinux", "8"): "almalinux8",
    ("almalinux", "9"): "almalinux9",
    ("rocky", "8"): "rl8",
    ("rocky linux", "8"): "rl8",
    ("rocky", "9"): "rl9",
    ("rocky linux", "9"): "rl9",
    ("centos", "7"): "centos7",
    ("centos", "8"): "centos8",
    ("centos stream", "8"): "cs8",
    ("centos stream", "9"): "cs9",
    ("ol", "7"): "ol7",
    ("ol", "8"): "ol8",
    ("ol", "9"): "ol9",
    ("oracle linux", "7"): "ol7",
    ("oracle linux", "8"): "ol8",
    ("oracle linux", "9"): "ol9",
    ("sles", "12"): "sle12",
    ("sles", "15"): "sle15",
    ("ubuntu", "20.04"): "ubuntu2004",
    ("ubuntu", "22.04"): "ubuntu2204",
    ("ubuntu", "24.04"): "ubuntu2404",
    ("debian", "11"): "debian11",
    ("debian", "12"): "debian12",
}

# Well-known compliance profiles catalog: (label, xccdf_profile_id_suffix)
PROFILE_CATALOG: list[tuple[str, str]] = [
    ("CIS Level 2 (default)",              "cis"),
    ("CIS Level 1 — Server",               "cis_server_l1"),
    ("CIS Level 1 — Workstation",          "cis_workstation_l1"),
    ("CIS Level 2 — Server",               "cis_server_l2"),
    ("CIS Level 2 — Workstation",          "cis_workstation_l2"),
    ("DISA STIG",                          "stig"),
    ("DISA STIG with GUI",                 "stig_gui"),
    ("NIST 800-53 / OSPP",                 "ospp"),
    ("PCI-DSS",                            "pci-dss"),
    ("PCI-DSS v4",                         "pci-dss_4"),
    ("HIPAA",                              "hipaa"),
    ("ANSSI BP-028 (Minimal)",             "anssi_bp28_minimal"),
    ("ANSSI BP-028 (Enhanced)",            "anssi_bp28_enhanced"),
    ("Australian ISM (Official)",          "ism_o"),
    ("Australian Essential Eight",         "e8"),
]

SSG_PREFIX = "xccdf_org.ssgproject.content_profile_"


class UnsupportedOSError(Exception):
    pass


def resolve_ssg_stem(os_id: str, version_id: str) -> str:
    """Map OS ID + version to SSG filename stem (without ssg- prefix and extension)."""
    key_full = (os_id.lower(), version_id.lower())
    if key_full in OS_MAP:
        return OS_MAP[key_full]
    major = version_id.split(".")[0]
    key_major = (os_id.lower(), major)
    if key_major in OS_MAP:
        return OS_MAP[key_major]
    raise UnsupportedOSError(
        f"OS not supported: id='{os_id}' version='{version_id}'. "
        f"Install scap-security-guide on the target and it will be used automatically."
    )


# SSG v0.1.76+ uses data stream format (ds.xml); older used xccdf.xml
_DS_SUFFIXES = ["-ds.xml", "-xccdf.xml", "-ds-1.2.xml"]


def resolve_bundled(os_id: str, version_id: str) -> Path | None:
    """Return path to bundled SSG content file in the Docker image."""
    try:
        stem = resolve_ssg_stem(os_id, version_id)
    except UnsupportedOSError:
        return None
    for suffix in _DS_SUFFIXES:
        candidate = BUNDLED_SSG_DIR / f"ssg-{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def system_content_path(os_id: str, version_id: str) -> str | None:
    """Return the expected SSG content path on the target system."""
    try:
        stem = resolve_ssg_stem(os_id, version_id)
    except UnsupportedOSError:
        return None
    base = "/usr/share/xml/scap/ssg/content"
    for suffix in _DS_SUFFIXES:
        return f"{base}/ssg-{stem}{suffix}"  # return first candidate, scanner will test
    return None


def resolve(os_id: str, version_id: str) -> Path | None:
    """Return the SSG content path from bundled files, or None if unavailable."""
    path = resolve_bundled(os_id, version_id)
    if path:
        log.info("Using bundled SSG content: %s", path)
    else:
        log.warning("No bundled SSG for %s %s", os_id, version_id)
    return path


def profile_label_to_id(label: str) -> str:
    """Convert a friendly label to full XCCDF profile ID."""
    for lbl, suffix in PROFILE_CATALOG:
        if lbl == label:
            return f"{SSG_PREFIX}{suffix}"
    if label.startswith("xccdf_"):
        return label
    return f"{SSG_PREFIX}{label}"


def list_profiles(xccdf_path: Path) -> list[dict]:
    NS = {
        "xccdf12": "http://checklists.nist.gov/xccdf/1.2",
        "xccdf11": "http://checklists.nist.gov/xccdf/1.1",
    }
    tree = ET.parse(xccdf_path)
    root = tree.getroot()
    tag = root.tag
    ns = NS["xccdf12"] if "1.2" in tag else NS["xccdf11"]
    profiles = []
    for p in root.findall(f".//{{{ns}}}Profile"):
        pid = p.get("id", "")
        title_el = p.find(f"{{{ns}}}title")
        title = (title_el.text or "") if title_el is not None else pid
        profiles.append({"id": pid, "title": title.strip()})
    return profiles


def list_bundled_oses() -> list[str]:
    """Return list of OS stems with bundled content available."""
    if not BUNDLED_SSG_DIR.exists():
        return []
    return [f.stem.replace("ssg-", "").replace("-xccdf", "")
            for f in BUNDLED_SSG_DIR.glob("ssg-*-xccdf.xml")]
