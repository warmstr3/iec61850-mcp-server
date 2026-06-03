"""
SEL RTAC .EXP Generator

Generates AcSELerator RTAC project export files (.EXP) containing:
- IEC 61850 GOOSE subscriber configuration
- Tag database entries (with IEC 61850 CDC-aware typing)
- Tag Processor mappings (GOOSE dataset → RTAC tags)
- IEC 61131-3 ST watchdog function block for GOOSE staleness detection
- Optional SV subscriber configuration

The .EXP format is XML-based and importable via:
  AcSELerator RTAC > File > Import Project
  AcRtacCmd importexp -p <project> -f <file.exp>
"""

import re
import json
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent
from typing import Any

from tools.scd_parser import (
    parse_scd_file,
    get_goose_control_blocks,
    get_sv_control_blocks,
)

# RTAC tag name constraints
MAX_TAG_NAME_LEN = 64
VALID_TAG_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# IEC 61850 CDC → RTAC data type mapping
# Maps common data class to (RTAC type, primary attribute)
CDC_TYPE_MAP = {
    # Status
    "SPS": ("SPS", "stVal"),      # Single Point Status
    "DPS": ("DPS", "stVal"),      # Double Point Status
    "INS": ("INS", "stVal"),      # Integer Status
    "ACT": ("SPS", "general"),    # Protection Activation
    "ACD": ("SPS", "general"),    # Directional Protection
    # Measurements
    "MV":  ("MV",  "mag.f"),      # Measured Value
    "CMV": ("CMV", "cVal.mag.f"), # Complex Measured Value
    "SAV": ("MV",  "instMag.f"),  # Sampled Analogue Value
    # Control
    "SPC": ("SPC", "stVal"),      # Single Point Control
    "DPC": ("DPC", "stVal"),      # Double Point Control
    # Binary
    "BOOLEAN": ("BOOLEAN", ""),
    "INT32":   ("INT32",   ""),
    "FLOAT32": ("FLOAT32", ""),
}


def _sanitize_tag_name(name: str, prefix: str = "") -> str:
    """Produce a valid RTAC tag name from a signal path."""
    # Replace non-alphanumeric (except underscore) with underscore
    clean = re.sub(r"[^A-Za-z0-9_]", "_", f"{prefix}{name}")
    # Must start with letter or underscore
    if clean and clean[0].isdigit():
        clean = "_" + clean
    # Truncate to max length
    return clean[:MAX_TAG_NAME_LEN]


def _infer_rtac_type(do_name: str, da_name: str, ln_class: str) -> str:
    """
    Infer RTAC data type from IEC 61850 logical node class and data object.
    Falls back to BOOLEAN for unknown protection signals.
    """
    # Protection trip/operate signals
    if ln_class in ("PTOC", "PDIF", "PDIS", "PDEF", "POVR", "PUVR", "PSCH"):
        if do_name in ("Op", "Str"):
            return "SPS"
    # Circuit breaker / switch
    if ln_class in ("XCBR", "XSWI"):
        if do_name == "Pos":
            return "DPS"
    # Autorecloser
    if ln_class == "RREC":
        return "SPS"
    # Measurements
    if do_name in ("Amp", "Vol", "W", "Var", "Hz", "PhV", "A"):
        return "MV"
    # Boolean fallback
    return "BOOLEAN"


def generate_rtac_tag_mapping(
    scd_path: str,
    gcb_ref: str,
    tag_prefix: str = "",
) -> dict[str, Any]:
    """
    Generate Tag Processor mapping rows for a GOOSE control block.
    Returns list of {source_tag, dest_tag, type, signal_path} entries.
    """
    # Parse gcb_ref: IED+LDInst/LLN0$GO$GCBName
    match = re.match(r"^(\w+?)(\w+)/LLN0\$GO\$(\w+)$", gcb_ref)
    if not match:
        return {"error": f"Cannot parse GoCB reference: {gcb_ref}"}

    ied_name = match.group(1)
    # Re-extract properly: iedName is everything before first LDevice inst
    # Try get_goose_control_blocks to resolve
    gcbs_result = get_goose_control_blocks(scd_path, ied_name)
    if "error" in gcbs_result:
        # Try splitting differently — ied name may include LD prefix
        # Fall back: parse all IEDs and search
        parsed = parse_scd_file(scd_path)
        gcbs_result = None
        for ied in parsed["ieds"]:
            candidate = get_goose_control_blocks(scd_path, ied["name"])
            for gcb in candidate.get("goose_control_blocks", []):
                if gcb.get("gcb_ref") == gcb_ref:
                    gcbs_result = candidate
                    ied_name = ied["name"]
                    break
            if gcbs_result:
                break
        if not gcbs_result:
            return {"error": f"GoCB '{gcb_ref}' not found in SCD"}

    gcb = next(
        (g for g in gcbs_result["goose_control_blocks"] if g.get("gcb_ref") == gcb_ref),
        None
    )
    if not gcb:
        return {"error": f"GoCB '{gcb_ref}' not found for IED '{ied_name}'"}

    mappings = []
    for i, member in enumerate(gcb.get("dataset_members", [])):
        ln_class = member.get("ln_class", "")
        do_name = member.get("do_name", "")
        da_name = member.get("da_name", "")
        signal_path = member.get("signal_path", "")

        rtac_type = _infer_rtac_type(do_name, da_name, ln_class)

        # Build readable tag name from signal components
        raw_name = f"{ln_class}{member.get('ln_inst','')}{do_name}"
        if da_name:
            raw_name += f"_{da_name.replace('.', '_')}"
        tag_name = _sanitize_tag_name(raw_name, tag_prefix)

        mappings.append({
            "index": i,
            "tag_name": tag_name,
            "rtac_type": rtac_type,
            "signal_path": signal_path,
            "ln_class": ln_class,
            "do_name": do_name,
            "da_name": da_name,
            "source_gcb": gcb_ref,
        })

    return {
        "gcb_ref": gcb_ref,
        "conf_rev": gcb.get("conf_rev", "1"),
        "app_id": gcb.get("app_id", ""),
        "mac_address": gcb.get("mac_address", ""),
        "mappings": mappings,
        "count": len(mappings),
    }


def generate_rtac_exp(
    scd_path: str,
    rtac_ied_name: str,
    goose_subscriptions: list[str],
    sv_subscriptions: list[str] = None,
    tag_prefix: str = "",
    output_path: str = "",
    include_watchdog: bool = True,
) -> dict[str, Any]:
    """
    Generate a complete .EXP file for AcSELerator RTAC.
    """
    sv_subscriptions = sv_subscriptions or []

    # Collect all tag mappings first
    all_mappings = []
    gcb_configs = []

    for gcb_ref in goose_subscriptions:
        mapping = generate_rtac_tag_mapping(scd_path, gcb_ref, tag_prefix)
        if "error" in mapping:
            return {"error": f"Failed mapping for {gcb_ref}: {mapping['error']}"}
        all_mappings.extend(mapping["mappings"])
        gcb_configs.append(mapping)

    # Build XML tree
    root = _build_exp_root(rtac_ied_name)
    _add_tag_database(root, all_mappings, gcb_configs, include_watchdog)
    _add_goose_clients(root, gcb_configs)
    _add_tag_processor(root, all_mappings, gcb_configs)

    if include_watchdog:
        _add_watchdog_pou(root, gcb_configs, tag_prefix)

    if sv_subscriptions:
        _add_sv_note(root, sv_subscriptions)

    # Serialize
    tree = ElementTree(root)
    indent(tree, space="  ")

    if output_path:
        tree.write(output_path, encoding="unicode", xml_declaration=True)

    # Return summary
    return {
        "status": "ok",
        "output_path": output_path,
        "rtac_ied_name": rtac_ied_name,
        "goose_subscriptions": goose_subscriptions,
        "total_tags": len(all_mappings) + (len(gcb_configs) if include_watchdog else 0),
        "watchdog_included": include_watchdog,
        "gcb_summary": [
            {
                "gcb_ref": m["gcb_ref"],
                "app_id": m["app_id"],
                "mac_address": m["mac_address"],
                "conf_rev": m["conf_rev"],
                "tag_count": m["count"],
            }
            for m in gcb_configs
        ],
    }


# ---------------------------------------------------------------------------
# XML builders
# ---------------------------------------------------------------------------

def _build_exp_root(rtac_ied_name: str) -> Element:
    root = Element("ACSELERATOR_RTAC_EXPORT")
    root.set("version", "1.0")
    root.set("generated", datetime.now(timezone.utc).isoformat())
    root.set("generator", "iec61850-mcp-server")

    meta = SubElement(root, "ProjectInfo")
    SubElement(meta, "ProjectName").text = rtac_ied_name
    SubElement(meta, "Description").text = (
        "Auto-generated IEC 61850 GOOSE subscriber configuration"
    )
    SubElement(meta, "CreatedBy").text = "IEC 61850 MCP Server"
    SubElement(meta, "CreatedAt").text = datetime.now(timezone.utc).isoformat()

    return root


def _add_tag_database(
    root: Element,
    all_mappings: list[dict],
    gcb_configs: list[dict],
    include_watchdog: bool,
) -> None:
    db = SubElement(root, "TagDatabase")

    # GOOSE data tags
    group = SubElement(db, "TagGroup")
    group.set("name", "IEC61850_GOOSE")

    for m in all_mappings:
        tag = SubElement(group, "Tag")
        tag.set("name", m["tag_name"])
        tag.set("type", m["rtac_type"])
        tag.set("description", m["signal_path"])
        tag.set("source", "IEC61850_GOOSE")

    # Watchdog tags — one BOOLEAN per GoCB
    if include_watchdog:
        wdg_group = SubElement(db, "TagGroup")
        wdg_group.set("name", "GOOSE_WATCHDOG")
        for gcb in gcb_configs:
            safe_name = re.sub(r"[^A-Za-z0-9_]", "_", gcb["gcb_ref"])[:50]
            for suffix, desc in [
                ("_STALE", "TRUE when GOOSE has not been received within MaxTime"),
                ("_COMM_FAIL", "TRUE when GOOSE communication has failed"),
                ("_ST_NUM", "Last received stNum value"),
                ("_SQ_NUM", "Last received sqNum value"),
            ]:
                wtag = SubElement(wdg_group, "Tag")
                wtag.set("name", f"WDG_{safe_name}{suffix}")
                wtag.set("type", "BOOLEAN" if "NUM" not in suffix else "INT32")
                wtag.set("description", desc)
                wtag.set("source", "IEC61131_LOGIC")


def _add_goose_clients(root: Element, gcb_configs: list[dict]) -> None:
    clients = SubElement(root, "ProtocolDrivers")
    drv = SubElement(clients, "IEC61850Driver")
    drv.set("role", "Client")

    for gcb in gcb_configs:
        sub = SubElement(drv, "GOOSESubscription")
        sub.set("GoCBRef", gcb["gcb_ref"])
        sub.set("AppID", gcb.get("app_id", "0x0000"))
        sub.set("MACAddress", gcb.get("mac_address", "01:0C:CD:01:00:00"))
        sub.set("ConfRev", gcb.get("conf_rev", "1"))

        # Dataset member types for the driver to decode
        ds_members = SubElement(sub, "DatasetMembers")
        for m in gcb["mappings"]:
            mem = SubElement(ds_members, "Member")
            mem.set("index", str(m["index"]))
            mem.set("signalPath", m["signal_path"])
            mem.set("rtacType", m["rtac_type"])
            mem.set("tagName", m["tag_name"])


def _add_tag_processor(
    root: Element,
    all_mappings: list[dict],
    gcb_configs: list[dict],
) -> None:
    tp = SubElement(root, "TagProcessor")
    tp.set("description", "Maps IEC 61850 GOOSE dataset members to RTAC tags")

    sheet = SubElement(tp, "MappingSheet")
    sheet.set("name", "GOOSE_Inputs")

    for m in all_mappings:
        row = SubElement(sheet, "Row")
        row.set("source", f"IEC61850.GOOSE.{m['source_gcb']}.{m['index']}")
        row.set("destination", m["tag_name"])
        row.set("type", m["rtac_type"])
        row.set("description", m["signal_path"])


def _add_watchdog_pou(
    root: Element,
    gcb_configs: list[dict],
    tag_prefix: str,
) -> None:
    """
    Add an IEC 61131-3 Structured Text function block that monitors
    GOOSE stNum/sqNum for staleness and comm failure.
    """
    pous = SubElement(root, "IEC61131_POUs")
    fb = SubElement(pous, "FunctionBlock")
    fb.set("name", "GOOSE_Watchdog")
    fb.set("language", "ST")
    fb.set("description", "Monitors GOOSE stNum/sqNum for staleness and communication failure")

    # Variable declarations
    decl = SubElement(fb, "Declaration")
    var_lines = ["VAR_INPUT"]
    var_lines.append("    Enable        : BOOL := TRUE;")
    var_lines.append("    StaleTimeout  : TIME := T#5S;   (* Alert after 5 s with no update *)")
    var_lines.append("    CommTimeout   : TIME := T#30S;  (* Comm fail after 30 s *)")
    var_lines.append("END_VAR")
    var_lines.append("")
    var_lines.append("VAR")

    for gcb in gcb_configs:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", gcb["gcb_ref"])[:40]
        var_lines.append(f"    (* --- {gcb['gcb_ref']} --- *)")
        var_lines.append(f"    {safe}_LastStNum    : INT := -1;")
        var_lines.append(f"    {safe}_LastSqNum    : INT := 0;")
        var_lines.append(f"    {safe}_LastUpdate   : TIME;")
        var_lines.append(f"    {safe}_StaleTimer   : TON;")
        var_lines.append(f"    {safe}_CommTimer    : TON;")

    var_lines.append("END_VAR")
    var_lines.append("")
    var_lines.append("VAR_OUTPUT")

    for gcb in gcb_configs:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", gcb["gcb_ref"])[:40]
        var_lines.append(f"    WDG_{safe}_STALE      : BOOL;")
        var_lines.append(f"    WDG_{safe}_COMM_FAIL  : BOOL;")
        var_lines.append(f"    WDG_{safe}_ST_NUM     : INT;")
        var_lines.append(f"    WDG_{safe}_SQ_NUM     : INT;")

    var_lines.append("END_VAR")
    decl.text = "\n".join(var_lines)

    # ST body
    body = SubElement(fb, "Body")
    st_lines = ["(* GOOSE Watchdog — auto-generated by IEC 61850 MCP Server *)"]
    st_lines.append("(* Monitors stNum/sqNum for each subscribed GoCB *)")
    st_lines.append("")

    for gcb in gcb_configs:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", gcb["gcb_ref"])[:40]
        app_id = gcb.get("app_id", "0x????")
        conf_rev = gcb.get("conf_rev", "?")
        st_lines.append(f"(* GoCB: {gcb['gcb_ref']}  AppID: {app_id}  confRev: {conf_rev} *)")
        st_lines.append(f"IF Enable THEN")
        st_lines.append(f"    (* Detect stNum change — new GOOSE retransmission burst *)")
        st_lines.append(f"    IF IEC61850.GOOSE['{gcb['gcb_ref']}'].stNum <> {safe}_LastStNum THEN")
        st_lines.append(f"        {safe}_LastStNum  := IEC61850.GOOSE['{gcb['gcb_ref']}'].stNum;")
        st_lines.append(f"        {safe}_LastSqNum  := IEC61850.GOOSE['{gcb['gcb_ref']}'].sqNum;")
        st_lines.append(f"        {safe}_LastUpdate := TIME();")
        st_lines.append(f"        {safe}_StaleTimer(IN := FALSE);  (* Reset stale timer *)")
        st_lines.append(f"        {safe}_CommTimer(IN := FALSE);   (* Reset comm timer *)")
        st_lines.append(f"    END_IF")
        st_lines.append(f"")
        st_lines.append(f"    (* Stale timer — fires if no retransmission within StaleTimeout *)")
        st_lines.append(f"    {safe}_StaleTimer(IN := TRUE, PT := StaleTimeout);")
        st_lines.append(f"    WDG_{safe}_STALE     := {safe}_StaleTimer.Q;")
        st_lines.append(f"")
        st_lines.append(f"    (* Comm fail timer — longer threshold for full alarm *)")
        st_lines.append(f"    {safe}_CommTimer(IN := TRUE, PT := CommTimeout);")
        st_lines.append(f"    WDG_{safe}_COMM_FAIL := {safe}_CommTimer.Q;")
        st_lines.append(f"")
        st_lines.append(f"    (* Pass through stNum/sqNum for diagnostics *)")
        st_lines.append(f"    WDG_{safe}_ST_NUM := IEC61850.GOOSE['{gcb['gcb_ref']}'].stNum;")
        st_lines.append(f"    WDG_{safe}_SQ_NUM := IEC61850.GOOSE['{gcb['gcb_ref']}'].sqNum;")
        st_lines.append(f"END_IF")
        st_lines.append("")

    body.text = "\n".join(st_lines)


def _add_sv_note(root: Element, sv_subscriptions: list[str]) -> None:
    note = SubElement(root, "SVSubscriptions")
    note.set("status", "pending")
    note.set(
        "note",
        "SV subscriptions listed below require additional MU sync configuration. "
        "Verify PTP/IEEE 1588 clock source before deployment."
    )
    for ref in sv_subscriptions:
        sv = SubElement(note, "SVSubscription")
        sv.set("SvCBRef", ref)
        sv.set("status", "manual_config_required")
