"""
Validator for RTAC .EXP files and GOOSE/SV configurations.

Checks:
- Tag name length and character constraints
- Duplicate AppIDs across subscriptions
- confRev consistency between EXP and SCD
- MAC address format (IEC 61850 multicast range)
- GOOSE retransmission timing sanity
- Required quality attributes on safety-critical signals
"""

import re
import xml.etree.ElementTree as ET
from typing import Any

from tools.scd_parser import parse_scd_file

MAX_TAG_NAME_LEN = 64
VALID_TAG_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# IEC 61850-8-1 reserved GOOSE multicast range: 01:0C:CD:01:00:00 – 01:0C:CD:01:01:FF
GOOSE_MAC_PATTERN = re.compile(
    r"^01:0C:CD:01:[01][0-9A-Fa-f]:[0-9A-Fa-f]{2}$", re.IGNORECASE
)
# SV multicast: 01:0C:CD:04:00:00 – 01:0C:CD:04:01:FF
SV_MAC_PATTERN = re.compile(
    r"^01:0C:CD:04:[01][0-9A-Fa-f]:[0-9A-Fa-f]{2}$", re.IGNORECASE
)

# Protection LN classes where quality attributes are safety-critical
PROTECTION_LN_CLASSES = {
    "PTOC", "PDIF", "PDIS", "PDEF", "POVR", "PUVR",
    "PSCH", "PHIZ", "PREC", "PTOV", "PTRC",
}


def validate_rtac_exp(exp_path: str, scd_path: str = None) -> dict[str, Any]:
    """
    Validate a .EXP file for RTAC import readiness.
    Returns a dict with 'errors', 'warnings', and 'info' lists.
    """
    errors = []
    warnings = []
    info = []

    try:
        tree = ET.parse(exp_path)
        root = tree.getroot()
    except ET.ParseError as e:
        return {"errors": [f"XML parse error: {e}"], "warnings": [], "info": []}

    # 1. Tag name validation
    tag_names_seen = {}
    for tag in root.iter("Tag"):
        name = tag.get("name", "")
        if not name:
            errors.append("Tag with empty name found")
            continue
        if len(name) > MAX_TAG_NAME_LEN:
            errors.append(
                f"Tag name too long ({len(name)} chars, max {MAX_TAG_NAME_LEN}): '{name}'"
            )
        if not VALID_TAG_RE.match(name):
            errors.append(
                f"Tag name contains invalid characters: '{name}' "
                f"(must start with letter/underscore, alphanumeric + underscore only)"
            )
        if name in tag_names_seen:
            errors.append(f"Duplicate tag name: '{name}'")
        tag_names_seen[name] = True
    info.append(f"Checked {len(tag_names_seen)} tag names")

    # 2. AppID uniqueness
    app_ids_seen = {}
    for sub in root.iter("GOOSESubscription"):
        app_id = sub.get("AppID", "").upper()
        gcb_ref = sub.get("GoCBRef", "")
        if not app_id:
            warnings.append(f"Missing AppID for subscription: {gcb_ref}")
            continue
        if app_id in app_ids_seen:
            errors.append(
                f"Duplicate AppID {app_id} on '{gcb_ref}' and '{app_ids_seen[app_id]}'"
            )
        else:
            app_ids_seen[app_id] = gcb_ref

    # 3. MAC address format
    for sub in root.iter("GOOSESubscription"):
        mac = sub.get("MACAddress", "")
        gcb_ref = sub.get("GoCBRef", "")
        if not mac:
            warnings.append(f"Missing MAC address for {gcb_ref}")
        elif not GOOSE_MAC_PATTERN.match(mac):
            warnings.append(
                f"MAC address '{mac}' for {gcb_ref} is outside IEC 61850 GOOSE "
                f"multicast range (01:0C:CD:01:00:00–01:0C:CD:01:01:FF)"
            )

    # 4. confRev cross-check against SCD
    if scd_path:
        try:
            parsed = parse_scd_file(scd_path)
            scd_conf_revs = {}
            for ied in parsed["ieds"]:
                for ld in ied["logical_devices"]:
                    for gcb in ld["goose_cbs"]:
                        ref = f"{ied['name']}{ld['inst']}/LLN0$GO${gcb['name']}"
                        scd_conf_revs[ref] = gcb.get("conf_rev", "1")

            for sub in root.iter("GOOSESubscription"):
                gcb_ref = sub.get("GoCBRef", "")
                exp_conf_rev = sub.get("ConfRev", "")
                scd_conf_rev = scd_conf_revs.get(gcb_ref)
                if scd_conf_rev is None:
                    warnings.append(
                        f"GoCB '{gcb_ref}' not found in SCD — may be a new/renamed IED"
                    )
                elif exp_conf_rev != scd_conf_rev:
                    errors.append(
                        f"confRev mismatch for '{gcb_ref}': "
                        f"EXP has {exp_conf_rev}, SCD has {scd_conf_rev}. "
                        f"GOOSE subscription will silently fail at runtime."
                    )
                else:
                    info.append(f"confRev OK for {gcb_ref}: {exp_conf_rev}")
        except Exception as e:
            warnings.append(f"Could not cross-check confRev against SCD: {e}")

    # 5. Protection signal quality attribute check
    for mem in root.iter("Member"):
        signal_path = mem.get("signalPath", "")
        rtac_type = mem.get("rtacType", "")
        # Extract LN class from signal path
        ln_match = re.search(r"/([A-Z]{2,6})\d*\.", signal_path)
        if ln_match:
            ln_class = ln_match.group(1)
            if ln_class in PROTECTION_LN_CLASSES and rtac_type == "BOOLEAN":
                warnings.append(
                    f"Protection signal '{signal_path}' mapped as raw BOOLEAN — "
                    f"consider using SPS type to preserve quality (q) attribute"
                )

    # 6. Missing dataset members
    for sub in root.iter("GOOSESubscription"):
        gcb_ref = sub.get("GoCBRef", "")
        ds_members = sub.find("DatasetMembers")
        if ds_members is None or len(list(ds_members)) == 0:
            errors.append(f"No dataset members configured for {gcb_ref}")

    # Summary
    status = "PASS" if not errors else "FAIL"
    return {
        "status": status,
        "exp_path": exp_path,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def validate_goose_config(scd_path: str, gcb_ref: str) -> dict[str, Any]:
    """
    Validate a GOOSE control block from an SCD file.
    """
    errors = []
    warnings = []
    info = []

    parsed = parse_scd_file(scd_path)

    # Find the GoCB
    target_gcb = None
    for ied in parsed["ieds"]:
        for ld in ied["logical_devices"]:
            for gcb in ld["goose_cbs"]:
                ref = f"{ied['name']}{ld['inst']}/LLN0$GO${gcb['name']}"
                if ref == gcb_ref:
                    target_gcb = gcb
                    target_ied = ied["name"]
                    target_ld = ld["inst"]
                    break

    if not target_gcb:
        return {
            "status": "FAIL",
            "errors": [f"GoCB '{gcb_ref}' not found in SCD"],
            "warnings": [],
            "info": [],
        }

    # AppID presence and format
    app_id = target_gcb.get("app_id", "")
    if not app_id:
        warnings.append("AppID not defined in Communication section — required for RTAC config")
    else:
        try:
            app_id_int = int(app_id, 16) if app_id.startswith("0x") else int(app_id, 16)
            if app_id_int > 0x3FFF:
                errors.append(
                    f"AppID {app_id} exceeds maximum GOOSE AppID range (0x0000–0x3FFF)"
                )
            info.append(f"AppID: {app_id}")
        except ValueError:
            errors.append(f"AppID '{app_id}' is not a valid hex value")

    # MAC address
    mac = target_gcb.get("mac_address", "")
    if not mac:
        warnings.append("MAC address not defined — required for RTAC subscriber config")
    elif not GOOSE_MAC_PATTERN.match(mac):
        errors.append(
            f"MAC address '{mac}' outside GOOSE multicast range 01:0C:CD:01:00:00–01:0C:CD:01:01:FF"
        )

    # VLAN
    vlan_id = target_gcb.get("vlan_id", "")
    vlan_priority = target_gcb.get("vlan_priority", "")
    if vlan_id:
        info.append(f"VLAN ID: {vlan_id}, Priority: {vlan_priority}")
    else:
        info.append("No VLAN tagging configured (untagged Ethernet)")

    # confRev
    conf_rev = target_gcb.get("conf_rev", "")
    if not conf_rev or conf_rev == "0":
        warnings.append(
            f"confRev is '{conf_rev}' — should be incremented when dataset changes"
        )
    else:
        info.append(f"confRev: {conf_rev}")

    # Retransmission timing
    min_time = target_gcb.get("min_time", "")
    max_time = target_gcb.get("max_time", "")
    if min_time and max_time:
        try:
            min_ms = int(min_time)
            max_ms = int(max_time)
            if min_ms < 2:
                warnings.append(f"MinTime {min_ms}ms is very aggressive — verify IED capability")
            if max_ms > 10000:
                warnings.append(
                    f"MaxTime {max_ms}ms is {max_ms/1000:.1f}s — "
                    f"set RTAC watchdog timeout > {max_ms/1000:.1f}s"
                )
            info.append(f"Retransmission: MinTime={min_ms}ms, MaxTime={max_ms}ms")
        except ValueError:
            pass

    # Dataset member count
    from tools.scd_parser import get_goose_control_blocks
    gcbs = get_goose_control_blocks(scd_path, target_ied)
    gcb_detail = next(
        (g for g in gcbs.get("goose_control_blocks", []) if g.get("gcb_ref") == gcb_ref),
        None
    )
    if gcb_detail:
        member_count = len(gcb_detail.get("dataset_members", []))
        if member_count == 0:
            errors.append("Dataset has no members — GOOSE will publish empty PDU")
        elif member_count > 64:
            warnings.append(
                f"Dataset has {member_count} members — consider splitting for performance"
            )
        else:
            info.append(f"Dataset members: {member_count}")

    status = "PASS" if not errors else "FAIL"
    return {
        "status": status,
        "gcb_ref": gcb_ref,
        "errors": errors,
        "warnings": warnings,
        "info": info,
    }
