"""
End-to-end test of the IEC 61850 MCP Server pipeline.

Tests:
  1. parse_scd_file          — SCD parsing
  2. get_goose_control_blocks — GoCB extraction with comms addresses
  3. generate_rtac_tag_mapping — Tag Processor row generation
  4. generate_rtac_exp        — Full .EXP file generation
  5. validate_rtac_exp        — .EXP validation with SCD cross-check

Run with:  python tests/test_pipeline.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.scd_parser import parse_scd_file, get_goose_control_blocks, get_sv_control_blocks
from tools.rtac_generator import generate_rtac_exp, generate_rtac_tag_mapping
from tools.validator import validate_rtac_exp, validate_goose_config
from tools.codesys_generator import generate_codesys_pou, generate_codesys_gvl

SCD_PATH = os.path.join(os.path.dirname(__file__), "../sample_data/meadowbrook_bay1.scd")
EXP_OUTPUT = "/tmp/RTAC1_bay1.exp"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"


def run(label, fn, *args, **kwargs):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = fn(*args, **kwargs)
    print(json.dumps(result, indent=2))
    return result


def test_parse_scd():
    result = run("1. parse_scd_file", parse_scd_file, SCD_PATH)
    assert result["ied_count"] == 3, f"Expected 3 IEDs, got {result['ied_count']}"
    names = [i["name"] for i in result["ieds"]]
    assert "PROT1" in names and "PROT2" in names and "RTAC1" in names
    print(f"\n{PASS} parse_scd_file: found {result['ied_count']} IEDs: {names}")
    return result


def test_get_goose_cbs():
    result = run("2. get_goose_control_blocks (PROT1)", get_goose_control_blocks, SCD_PATH, "PROT1")
    assert "error" not in result, result.get("error")
    assert result["count"] == 2, f"Expected 2 GoCBs, got {result['count']}"
    gcb = result["goose_control_blocks"][0]
    assert gcb["app_id"] in ("0001", "0002"), f"AppID not resolved: {gcb['app_id']}"
    assert gcb["mac_address"].startswith("01:0C:CD:01"), f"Bad MAC: {gcb['mac_address']}"
    assert len(gcb["dataset_members"]) > 0, "No dataset members resolved"
    print(f"\n{PASS} get_goose_control_blocks: {result['count']} GoCBs, "
          f"first has {len(gcb['dataset_members'])} members, AppID={gcb['app_id']}")
    return result


def test_get_sv_cbs():
    result = run("3. get_sv_control_blocks (PROT1)", get_sv_control_blocks, SCD_PATH, "PROT1")
    print(f"\n{PASS} get_sv_control_blocks: {result['count']} SvCBs (expected 0 in sample)")
    return result


def test_tag_mapping():
    gcb_ref = "PROT1LD0/LLN0$GO$GCB_PROT"
    result = run("4. generate_rtac_tag_mapping", generate_rtac_tag_mapping,
                 SCD_PATH, gcb_ref, "BAY1_")
    assert "error" not in result, result.get("error")
    assert result["count"] > 0, "No tag mappings generated"
    for m in result["mappings"]:
        name = m["tag_name"]
        assert len(name) <= 64, f"Tag too long: {name}"
        assert name.replace("_", "").isalnum(), f"Invalid chars in tag: {name}"
    print(f"\n{PASS} generate_rtac_tag_mapping: {result['count']} tags generated")
    return result


def test_generate_exp():
    result = run(
        "5. generate_rtac_exp",
        generate_rtac_exp,
        scd_path=SCD_PATH,
        rtac_ied_name="RTAC1",
        goose_subscriptions=[
            "PROT1LD0/LLN0$GO$GCB_PROT",
            "PROT1LD0/LLN0$GO$GCB_STATUS",
            "PROT2LD0/LLN0$GO$GCB_BUS",
        ],
        sv_subscriptions=[],
        tag_prefix="BAY1_",
        output_path=EXP_OUTPUT,
        include_watchdog=True,
    )
    assert result["status"] == "ok", f"EXP generation failed: {result}"
    assert os.path.exists(EXP_OUTPUT), f"Output file not written: {EXP_OUTPUT}"
    file_size = os.path.getsize(EXP_OUTPUT)
    assert file_size > 500, f"Output file suspiciously small: {file_size} bytes"
    print(f"\n{PASS} generate_rtac_exp: {file_size} byte .EXP written to {EXP_OUTPUT}")
    return result


def test_validate_exp():
    result = run("6. validate_rtac_exp", validate_rtac_exp, EXP_OUTPUT, SCD_PATH)
    print(f"\n{'PASS' if result['status'] == 'PASS' else 'WARN'} validate_rtac_exp: "
          f"{result['error_count']} errors, {result['warning_count']} warnings")
    for e in result["errors"]:
        print(f"  {FAIL} ERROR: {e}")
    for w in result["warnings"]:
        print(f"  ⚠  WARN:  {w}")
    return result


def test_validate_goose():
    result = run("7. validate_goose_config", validate_goose_config,
                 SCD_PATH, "PROT1LD0/LLN0$GO$GCB_PROT")
    print(f"\n{PASS if result['status'] == 'PASS' else FAIL} validate_goose_config: {result['status']}")
    return result


def test_codesys_pou():
    result = run(
        "8. generate_codesys_pou",
        generate_codesys_pou,
        scd_path=SCD_PATH,
        goose_subscriptions=[
            "PROT1LD0/LLN0$GO$GCB_PROT",
            "PROT1LD0/LLN0$GO$GCB_STATUS",
            "PROT2LD0/LLN0$GO$GCB_BUS",
        ],
        tag_prefix="BAY1_",
        pou_name="FB_GOOSE_Bay1",
        include_watchdog=True,
        include_quality=True,
    )
    assert "error" not in result, result.get("error")
    assert result["declaration"], "Empty declaration"
    assert result["implementation"], "Empty implementation"
    assert len(result["toolkit_steps"]) == 7, f"Expected 7 toolkit steps, got {len(result['toolkit_steps'])}"

    # Verify declaration contains expected sections
    decl = result["declaration"]
    assert "VAR_INPUT" in decl
    assert "VAR_OUTPUT" in decl
    assert "TON" in decl, "Missing timer declarations"

    # Verify implementation contains expected structure
    impl = result["implementation"]
    assert "IF NOT bEnable" in impl
    assert "WDG_" in impl
    assert "_tmrStale_" in impl

    print(f"\n{PASS} generate_codesys_pou:")
    print(f"  POU:        {result['pou_name']} ({result['pou_type']}, {result['language']})")
    print(f"  Variables:  {len(result['variables'])} total")
    print(f"  GVL:        {result['gvl_name']}")
    print(f"  Steps:      {len(result['toolkit_steps'])} toolkit calls")
    print(f"\n--- DECLARATION (first 20 lines) ---")
    for line in result["declaration"].splitlines()[:20]:
        print(f"  {line}")
    print(f"\n--- IMPLEMENTATION (first 25 lines) ---")
    for line in result["implementation"].splitlines()[:25]:
        print(f"  {line}")
    print(f"\n--- TOOLKIT STEPS ---")
    for step in result["toolkit_steps"]:
        print(f"  Step {step['step']}: {step['tool']} — {step['description']}")
    return result


def test_codesys_gvl():
    result = run(
        "9. generate_codesys_gvl",
        generate_codesys_gvl,
        scd_path=SCD_PATH,
        goose_subscriptions=["PROT1LD0/LLN0$GO$GCB_PROT"],
        tag_prefix="BAY1_",
        gvl_name="GVL_GOOSE_Bay1",
    )
    assert "error" not in result, result.get("error")
    assert "VAR_GLOBAL" in result["declaration"]
    print(f"\n{PASS} generate_codesys_gvl: {result['gvl_name']}")
    print(f"\n--- GVL DECLARATION ---")
    for line in result["declaration"].splitlines():
        print(f"  {line}")
    return result


def preview_exp():
    """Print the first 80 lines of the generated EXP for inspection."""
    print(f"\n{'='*60}")
    print(f"  Generated .EXP file preview (first 80 lines)")
    print(f"{'='*60}")
    with open(EXP_OUTPUT) as f:
        for i, line in enumerate(f):
            if i >= 80:
                print("  ... (truncated)")
                break
            print(f"  {line}", end="")


if __name__ == "__main__":
    print("\nIEC 61850 MCP Server — End-to-End Pipeline Test")
    print(f"SCD: {SCD_PATH}")

    try:
        test_parse_scd()
        test_get_goose_cbs()
        test_get_sv_cbs()
        test_tag_mapping()
        test_generate_exp()
        test_validate_exp()
        test_validate_goose()
        test_codesys_pou()
        test_codesys_gvl()
        preview_exp()
        print(f"\n\n{PASS} All tests passed.\n")
    except AssertionError as e:
        print(f"\n{FAIL} Test failed: {e}\n")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n{FAIL} Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)
