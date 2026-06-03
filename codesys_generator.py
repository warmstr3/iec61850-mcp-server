"""
CODESYS POU Generator for IEC 61850 GOOSE/SV

Produces structured output directly consumable by @codesys/mcp-toolkit:
  - declaration: the VAR block text for set_pou_code(declaration=...)
  - implementation: the ST body text for set_pou_code(implementation=...)
  - gvl_declaration: a Global Variable List for cross-POU tag sharing
  - toolkit_steps: ordered list of exact toolkit calls to make

CODESYS IEC 61131-3 type mapping for IEC 61850 CDCs:
  SPS  → BOOL  (stVal) + WORD (quality)
  DPS  → BYTE  (stVal: 0=intermediate,1=off,2=on,3=bad)
  MV   → REAL  (mag) + WORD (quality)
  INS  → DINT
  ACT  → BOOL  (general)
"""

import re
from typing import Any

from tools.scd_parser import get_goose_control_blocks, get_sv_control_blocks
from tools.rtac_generator import generate_rtac_tag_mapping

# IEC 61850 CDC → CODESYS/IEC 61131-3 type
# Each entry: (primary_type, quality_type, description)
CDC_TO_ST: dict[str, tuple[str, str, str]] = {
    "SPS":  ("BOOL",  "WORD",   "Single-point status"),
    "DPS":  ("BYTE",  "WORD",   "Double-point status: 0=int,1=off,2=on,3=bad"),
    "MV":   ("REAL",  "WORD",   "Measured value (magnitude)"),
    "CMV":  ("REAL",  "WORD",   "Complex measured value (magnitude)"),
    "SAV":  ("REAL",  "WORD",   "Sampled analogue value"),
    "INS":  ("DINT",  "WORD",   "Integer status"),
    "ACT":  ("BOOL",  "WORD",   "Protection activation"),
    "ACD":  ("BOOL",  "WORD",   "Directional protection activation"),
    "BOOLEAN": ("BOOL", "",     "Raw boolean"),
    "INT32":   ("DINT", "",     "Raw integer"),
    "FLOAT32": ("REAL", "",     "Raw float"),
}

# Maps RTAC types (from rtac_generator) to CODESYS ST types
RTAC_TO_ST = {
    "SPS":     "BOOL",
    "DPS":     "BYTE",
    "MV":      "REAL",
    "CMV":     "REAL",
    "INS":     "DINT",
    "SPC":     "BOOL",
    "DPC":     "BYTE",
    "BOOLEAN": "BOOL",
    "INT32":   "DINT",
    "FLOAT32": "REAL",
}


def _safe(name: str) -> str:
    """Make a valid IEC 61131-3 identifier (max 31 chars for CODESYS)."""
    clean = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if clean and clean[0].isdigit():
        clean = "_" + clean
    return clean[:31]


def generate_codesys_pou(
    scd_path: str,
    goose_subscriptions: list[str],
    tag_prefix: str = "",
    pou_name: str = "GOOSE_Subscriber",
    include_watchdog: bool = True,
    include_quality: bool = True,
) -> dict[str, Any]:
    """
    Generate a complete CODESYS Function Block for GOOSE subscription.

    Returns a dict with:
      pou_name       : suggested name for create_pou tool call
      pou_type       : always "FUNCTION_BLOCK"
      language       : always "ST"
      declaration    : full VAR block — pass to set_pou_code(declaration=...)
      implementation : full ST body  — pass to set_pou_code(implementation=...)
      gvl_name       : suggested GVL name
      gvl_declaration: GVL text for the global tag list (optional companion)
      variables      : structured list of all variables (for reference)
      toolkit_steps  : ordered list of codesys/mcp-toolkit calls to make
    """
    # Collect all mappings across subscriptions
    all_gcb_configs = []
    for gcb_ref in goose_subscriptions:
        mapping = generate_rtac_tag_mapping(scd_path, gcb_ref, tag_prefix)
        if "error" in mapping:
            return {"error": f"Failed mapping {gcb_ref}: {mapping['error']}"}
        all_gcb_configs.append(mapping)

    variables = _build_variable_list(all_gcb_configs, include_quality, include_watchdog)
    declaration = _build_declaration(variables, all_gcb_configs, include_watchdog)
    implementation = _build_implementation(all_gcb_configs, variables, include_watchdog)
    gvl_name = f"GVL_{pou_name}"
    gvl_declaration = _build_gvl(variables, pou_name)
    toolkit_steps = _build_toolkit_steps(pou_name, gvl_name, declaration, implementation, gvl_declaration)

    return {
        "pou_name": pou_name,
        "pou_type": "FUNCTION_BLOCK",
        "language": "ST",
        "declaration": declaration,
        "implementation": implementation,
        "gvl_name": gvl_name,
        "gvl_declaration": gvl_declaration,
        "variables": variables,
        "toolkit_steps": toolkit_steps,
        "gcb_summary": [
            {
                "gcb_ref": g["gcb_ref"],
                "app_id": g.get("app_id", ""),
                "conf_rev": g.get("conf_rev", ""),
                "tag_count": g["count"],
            }
            for g in all_gcb_configs
        ],
    }


def generate_codesys_gvl(
    scd_path: str,
    goose_subscriptions: list[str],
    tag_prefix: str = "",
    gvl_name: str = "GVL_GOOSE",
) -> dict[str, Any]:
    """
    Generate a CODESYS Global Variable List declaration for all GOOSE tags.
    This is useful when GOOSE values need to be shared across multiple POUs.
    Returns gvl_name and declaration for the toolkit's set_pou_code call on the GVL object.
    """
    all_gcb_configs = []
    for gcb_ref in goose_subscriptions:
        mapping = generate_rtac_tag_mapping(scd_path, gcb_ref, tag_prefix)
        if "error" in mapping:
            return {"error": f"Failed mapping {gcb_ref}: {mapping['error']}"}
        all_gcb_configs.append(mapping)

    variables = _build_variable_list(all_gcb_configs, include_quality=True, include_watchdog=True)
    gvl_declaration = _build_gvl(variables, gvl_name)

    return {
        "gvl_name": gvl_name,
        "declaration": gvl_declaration,
        "toolkit_steps": [
            {
                "step": 1,
                "tool": "create_pou",
                "description": f"Create Global Variable List '{gvl_name}'",
                "params": {
                    "name": gvl_name,
                    "type": "GVL",
                    "project_path": "<your_project.project>",
                    "parent_path": "Application",
                },
            },
            {
                "step": 2,
                "tool": "set_pou_code",
                "description": f"Write GVL variable declarations",
                "params": {
                    "project_path": "<your_project.project>",
                    "pou_path": f"Application/{gvl_name}",
                    "declaration": gvl_declaration,
                    "implementation": "",
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _build_variable_list(
    gcb_configs: list[dict],
    include_quality: bool,
    include_watchdog: bool,
) -> list[dict]:
    """Build a flat list of all variables needed."""
    variables = []

    # Data variables from GOOSE dataset members
    for gcb in gcb_configs:
        safe_gcb = _safe(gcb["gcb_ref"])
        for m in gcb["mappings"]:
            st_type = RTAC_TO_ST.get(m["rtac_type"], "BOOL")
            tag = _safe(m["tag_name"])

            variables.append({
                "name": tag,
                "st_type": st_type,
                "section": "VAR_OUTPUT",
                "comment": m["signal_path"],
                "gcb_ref": gcb["gcb_ref"],
                "index": m["index"],
                "kind": "data",
            })

            # Quality companion variable (q attribute)
            if include_quality and m.get("da_name") not in ("q", "quality"):
                variables.append({
                    "name": f"{tag}_Q",
                    "st_type": "WORD",
                    "section": "VAR_OUTPUT",
                    "comment": f"Quality flags for {m['signal_path']}",
                    "gcb_ref": gcb["gcb_ref"],
                    "index": m["index"],
                    "kind": "quality",
                })

        # Watchdog variables per GoCB
        if include_watchdog:
            safe = _safe(gcb["gcb_ref"])[:24]
            for vname, vtype, vcomment in [
                (f"WDG_{safe}_STALE",     "BOOL",  f"TRUE when {gcb['gcb_ref']} GOOSE not received within MaxTime"),
                (f"WDG_{safe}_CFAIL",     "BOOL",  f"TRUE when {gcb['gcb_ref']} communication has failed"),
                (f"WDG_{safe}_STNUM",     "DWORD", f"Last stNum from {gcb['gcb_ref']}"),
                (f"WDG_{safe}_SQNUM",     "DWORD", f"Last sqNum from {gcb['gcb_ref']}"),
                (f"WDG_{safe}_LAST_RX",   "DWORD", f"Timestamp of last GOOSE received (ms since boot)"),
            ]:
                variables.append({
                    "name": _safe(vname),
                    "st_type": vtype,
                    "section": "VAR_OUTPUT",
                    "comment": vcomment,
                    "gcb_ref": gcb["gcb_ref"],
                    "kind": "watchdog",
                })

    # Internal state variables for watchdog timers
    if include_watchdog:
        for gcb in gcb_configs:
            safe = _safe(gcb["gcb_ref"])[:24]
            variables.append({
                "name": f"_tmrStale_{safe}",
                "st_type": "TON",
                "section": "VAR",
                "comment": f"Staleness timer for {gcb['gcb_ref']}",
                "gcb_ref": gcb["gcb_ref"],
                "kind": "internal",
            })
            variables.append({
                "name": f"_tmrCFail_{safe}",
                "st_type": "TON",
                "section": "VAR",
                "comment": f"Comm-fail timer for {gcb['gcb_ref']}",
                "gcb_ref": gcb["gcb_ref"],
                "kind": "internal",
            })
            variables.append({
                "name": f"_lastStNum_{safe}",
                "st_type": "DWORD",
                "section": "VAR",
                "comment": f"Previous stNum for change detection",
                "gcb_ref": gcb["gcb_ref"],
                "kind": "internal",
            })

    return variables


def _build_declaration(
    variables: list[dict],
    gcb_configs: list[dict],
    include_watchdog: bool,
) -> str:
    """
    Build the full CODESYS FB declaration block.
    @codesys/mcp-toolkit expects the entire declaration including FUNCTION_BLOCK header.
    """
    lines = []

    # Group by section
    sections: dict[str, list[dict]] = {}
    for v in variables:
        sections.setdefault(v["section"], []).append(v)

    # VAR_INPUT
    lines.append("VAR_INPUT")
    lines.append("    bEnable         : BOOL := TRUE;         (* Enable watchdog monitoring *)")
    lines.append("    tStaleTimeout   : TIME := T#5S;         (* Staleness alarm threshold *)")
    lines.append("    tCommFailTimeout: TIME := T#30S;        (* Comm-fail alarm threshold *)")
    lines.append("END_VAR")
    lines.append("")

    # VAR_OUTPUT — data + watchdog outputs
    lines.append("VAR_OUTPUT")
    for v in variables:
        if v["section"] == "VAR_OUTPUT":
            pad = max(1, 32 - len(v["name"]))
            lines.append(f"    {v['name']}{' ' * pad}: {v['st_type']};  (* {v['comment']} *)")
    lines.append("END_VAR")
    lines.append("")

    # VAR — internal timers and state
    internals = [v for v in variables if v["section"] == "VAR"]
    if internals:
        lines.append("VAR")
        for v in internals:
            pad = max(1, 32 - len(v["name"]))
            lines.append(f"    {v['name']}{' ' * pad}: {v['st_type']};  (* {v['comment']} *)")
        lines.append("END_VAR")

    return "\n".join(lines)


def _build_implementation(
    gcb_configs: list[dict],
    variables: list[dict],
    include_watchdog: bool,
) -> str:
    """
    Build the ST implementation body.
    Uses the CODESYS IEC 61850 library function block naming conventions.
    """
    lines = [
        "(* =========================================================== *)",
        "(* GOOSE Subscriber — auto-generated by IEC 61850 MCP Server    *)",
        "(*                                                               *)",
        "(* Requires: IEC61850 library in CODESYS Library Manager        *)",
        "(*   or equivalent vendor GOOSE FB library                       *)",
        "(* =========================================================== *)",
        "",
        "IF NOT bEnable THEN",
        "    RETURN;",
        "END_IF",
        "",
    ]

    for gcb in gcb_configs:
        gcb_ref = gcb["gcb_ref"]
        safe = _safe(gcb_ref)[:24]
        app_id = gcb.get("app_id", "0x0000")
        conf_rev = gcb.get("conf_rev", "1")
        mac = gcb.get("mac_address", "01:0C:CD:01:00:00")

        lines.append(f"(* --- GoCB: {gcb_ref} ---")
        lines.append(f"     AppID: {app_id}  confRev: {conf_rev}  MAC: {mac} *)")
        lines.append("")

        # Read GOOSE data — placeholder for actual IEC 61850 lib call
        lines.append(f"(* Read dataset members from incoming GOOSE *)")
        for m in gcb["mappings"]:
            st_type = RTAC_TO_ST.get(m["rtac_type"], "BOOL")
            tag = _safe(m["tag_name"])
            lines.append(
                f"(* [{m['index']}] {m['signal_path']} → {tag} : {st_type} *)"
            )

        lines.append("")

        if include_watchdog:
            lines.append(f"(* --- Watchdog: stNum change detection --- *)")
            lines.append(f"IF _lastStNum_{safe} <> WDG_{safe}_STNUM THEN")
            lines.append(f"    _lastStNum_{safe}  := WDG_{safe}_STNUM;")
            lines.append(f"    WDG_{safe}_LAST_RX := DWORD_TO_DWORD(0);  (* Replace with SysTimeGetMs() *)")
            lines.append(f"    _tmrStale_{safe}(IN := FALSE);   (* Reset stale timer on new data *)")
            lines.append(f"    _tmrCFail_{safe}(IN := FALSE);")
            lines.append(f"END_IF")
            lines.append("")
            lines.append(f"(* Staleness timer: fires if no GOOSE retransmission within tStaleTimeout *)")
            lines.append(f"_tmrStale_{safe}(IN := TRUE, PT := tStaleTimeout);")
            lines.append(f"WDG_{safe}_STALE := _tmrStale_{safe}.Q;")
            lines.append("")
            lines.append(f"(* Comm-fail timer: longer threshold for hard alarm *)")
            lines.append(f"_tmrCFail_{safe}(IN := TRUE, PT := tCommFailTimeout);")
            lines.append(f"WDG_{safe}_CFAIL := _tmrCFail_{safe}.Q;")
            lines.append("")

    lines.append("(* =========================================================== *)")
    lines.append("(* NOTE: Replace the dataset member read placeholders above     *)")
    lines.append("(* with your actual GOOSE library calls. Common approaches:     *)")
    lines.append("(*                                                               *)")
    lines.append("(* Option A — CODESYS IEC 61850 lib (if available):             *)")
    lines.append("(*   fbGoose.AppID    := 16#0001;                               *)")
    lines.append("(*   fbGoose.Execute  := TRUE;                                  *)")
    lines.append("(*   myTag            := fbGoose.DataSet[0];                    *)")
    lines.append("(*                                                               *)")
    lines.append("(* Option B — Direct Ethernet frame parsing (IEC 61850-8-1):    *)")
    lines.append("(*   Use SysSocket + manual ASN.1 BER decode of GOOSE PDU       *)")
    lines.append("(*                                                               *)")
    lines.append("(* Option C — Via SEL RTAC Tag Processor (if bridged):          *)")
    lines.append("(*   Tags are populated externally; read from GVL directly      *)")
    lines.append("(* =========================================================== *)")

    return "\n".join(lines)


def _build_gvl(variables: list[dict], pou_name: str) -> str:
    """Build a Global Variable List declaration for cross-POU tag sharing."""
    lines = [
        f"(* Global Variable List — IEC 61850 GOOSE tags from {pou_name} *)",
        f"(* Auto-generated by IEC 61850 MCP Server *)",
        "",
        "VAR_GLOBAL",
    ]
    for v in variables:
        if v["section"] == "VAR_OUTPUT" and v["kind"] in ("data", "watchdog"):
            pad = max(1, 32 - len(v["name"]))
            lines.append(f"    {v['name']}{' ' * pad}: {v['st_type']};  (* {v['comment']} *)")
    lines.append("END_VAR")
    return "\n".join(lines)


def _build_toolkit_steps(
    pou_name: str,
    gvl_name: str,
    declaration: str,
    implementation: str,
    gvl_declaration: str,
) -> list[dict]:
    """
    Return the ordered list of @codesys/mcp-toolkit calls.
    Tool names match exactly what the toolkit exposes.
    """
    return [
        {
            "step": 1,
            "tool": "create_project",
            "description": "Create a new CODESYS project (skip if opening existing)",
            "params": {
                "project_path": "C:/Projects/IEC61850_Bay1.project",
            },
            "note": "Use open_project instead if the project already exists",
        },
        {
            "step": 2,
            "tool": "create_pou",
            "description": f"Create the GOOSE subscriber Function Block '{pou_name}'",
            "params": {
                "project_path": "<your_project.project>",
                "name": pou_name,
                "type": "FUNCTION_BLOCK",
                "parent_path": "Application",
                "language": "ST",
            },
        },
        {
            "step": 3,
            "tool": "set_pou_code",
            "description": f"Write declaration and implementation to '{pou_name}'",
            "params": {
                "project_path": "<your_project.project>",
                "pou_path": f"Application/{pou_name}",
                "declaration": declaration,
                "implementation": implementation,
            },
        },
        {
            "step": 4,
            "tool": "create_pou",
            "description": f"Create Global Variable List '{gvl_name}' (optional, for cross-POU sharing)",
            "params": {
                "project_path": "<your_project.project>",
                "name": gvl_name,
                "type": "GVL",
                "parent_path": "Application",
            },
        },
        {
            "step": 5,
            "tool": "set_pou_code",
            "description": f"Write GVL declarations to '{gvl_name}'",
            "params": {
                "project_path": "<your_project.project>",
                "pou_path": f"Application/{gvl_name}",
                "declaration": gvl_declaration,
                "implementation": "",
            },
        },
        {
            "step": 6,
            "tool": "compile_project",
            "description": "Compile and check for errors — feed any diagnostics back for auto-correction",
            "params": {
                "project_path": "<your_project.project>",
            },
            "note": (
                "If compilation fails, read the error messages and call set_pou_code again "
                "with corrections. Typical issues: undeclared GOOSE library FBs, "
                "type mismatches on DPS BYTE assignments."
            ),
        },
        {
            "step": 7,
            "tool": "save_project",
            "description": "Save the project",
            "params": {
                "project_path": "<your_project.project>",
            },
        },
    ]
