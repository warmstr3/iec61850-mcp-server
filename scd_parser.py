"""
SCD/SSD/ICD Parser for IEC 61850 MCP Server

Parses Substation Configuration Description files and extracts:
- IED list and capabilities
- Logical nodes and data objects
- Datasets
- GOOSE Control Blocks (GoCB)
- Sampled Value Control Blocks (SvCB)
"""

import xml.etree.ElementTree as ET
from typing import Any

# IEC 61850 SCL namespace
SCL_NS = "http://www.iec.ch/61850/2003/SCL"
NS = {"scl": SCL_NS}


def _tag(local: str) -> str:
    return f"{{{SCL_NS}}}{local}"


def parse_scd_file(path: str) -> dict[str, Any]:
    """
    Parse an SCD/SSD/ICD file and return a summary of all
    IEDs, logical nodes, datasets, GoCBs, and SvCBs.
    """
    tree = ET.parse(path)
    root = tree.getroot()

    ieds = []
    for ied in root.iter(_tag("IED")):
        ied_name = ied.get("name", "")
        ied_desc = ied.get("desc", "")

        # Collect access points
        access_points = [ap.get("name") for ap in ied.iter(_tag("AccessPoint"))]

        # Collect logical devices
        logical_devices = []
        for ld in ied.iter(_tag("LDevice")):
            inst = ld.get("inst", "")
            lnodes = []
            for ln in ld.iter(_tag("LN")):
                lnodes.append({
                    "class": ln.get("lnClass", ""),
                    "inst": ln.get("inst", ""),
                    "prefix": ln.get("prefix", ""),
                })
            # Also grab LN0
            ln0 = ld.find(_tag("LN0"))
            if ln0 is not None:
                lnodes.insert(0, {
                    "class": "LLN0",
                    "inst": "",
                    "prefix": "",
                })
            logical_devices.append({
                "inst": inst,
                "logical_nodes": lnodes,
                "goose_cbs": _extract_goose_cbs(ld, ied_name),
                "sv_cbs": _extract_sv_cbs(ld, ied_name),
                "datasets": _extract_datasets(ld, ied_name),
            })

        ieds.append({
            "name": ied_name,
            "desc": ied_desc,
            "access_points": access_points,
            "logical_devices": logical_devices,
        })

    # Extract Communication section for GSE/SMV addresses
    comm_map = _extract_communication(root)

    # Merge communication addresses into GoCBs/SvCBs
    for ied in ieds:
        for ld in ied["logical_devices"]:
            for gcb in ld["goose_cbs"]:
                key = (ied["name"], ld["inst"], gcb["name"])
                if key in comm_map.get("gse", {}):
                    gcb.update(comm_map["gse"][key])
            for svcb in ld["sv_cbs"]:
                key = (ied["name"], ld["inst"], svcb["name"])
                if key in comm_map.get("smv", {}):
                    svcb.update(comm_map["smv"][key])

    return {
        "file": path,
        "ied_count": len(ieds),
        "ieds": ieds,
    }


def get_goose_control_blocks(scd_path: str, ied_name: str) -> dict[str, Any]:
    """
    Return all GOOSE control blocks for a named IED,
    with full dataset member details.
    """
    parsed = parse_scd_file(scd_path)

    ied = next((i for i in parsed["ieds"] if i["name"] == ied_name), None)
    if not ied:
        return {
            "error": f"IED '{ied_name}' not found. Available: {[i['name'] for i in parsed['ieds']]}"
        }

    results = []
    for ld in ied["logical_devices"]:
        for gcb in ld["goose_cbs"]:
            # Resolve dataset members
            ds_ref = gcb.get("dataset_ref", "")
            ds_name = ds_ref.split("$")[-1] if "$" in ds_ref else ds_ref
            members = _resolve_dataset_members(
                scd_path, ied_name, ld["inst"], ds_name
            )
            gcb_full = dict(gcb)
            gcb_full["dataset_members"] = members
            gcb_full["ld_inst"] = ld["inst"]
            # Full GoCB reference for RTAC config
            gcb_full["gcb_ref"] = f"{ied_name}{ld['inst']}/LLN0$GO${gcb['name']}"
            results.append(gcb_full)

    return {
        "ied_name": ied_name,
        "goose_control_blocks": results,
        "count": len(results),
    }


def get_sv_control_blocks(scd_path: str, ied_name: str) -> dict[str, Any]:
    """
    Return all Sampled Value control blocks for a named IED.
    """
    parsed = parse_scd_file(scd_path)

    ied = next((i for i in parsed["ieds"] if i["name"] == ied_name), None)
    if not ied:
        return {
            "error": f"IED '{ied_name}' not found. Available: {[i['name'] for i in parsed['ieds']]}"
        }

    results = []
    for ld in ied["logical_devices"]:
        for svcb in ld["sv_cbs"]:
            ds_ref = svcb.get("dataset_ref", "")
            ds_name = ds_ref.split("$")[-1] if "$" in ds_ref else ds_ref
            members = _resolve_dataset_members(
                scd_path, ied_name, ld["inst"], ds_name
            )
            svcb_full = dict(svcb)
            svcb_full["dataset_members"] = members
            svcb_full["ld_inst"] = ld["inst"]
            svcb_full["svcb_ref"] = f"{ied_name}{ld['inst']}/LLN0$SV${svcb['name']}"
            results.append(svcb_full)

    return {
        "ied_name": ied_name,
        "sv_control_blocks": results,
        "count": len(results),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_goose_cbs(ld_elem: ET.Element, ied_name: str) -> list[dict]:
    gcbs = []
    ln0 = ld_elem.find(_tag("LN0"))
    if ln0 is None:
        return gcbs
    for gcb in ln0.iter(_tag("GSEControl")):
        gcbs.append({
            "name": gcb.get("name", ""),
            "desc": gcb.get("desc", ""),
            "dataset_ref": gcb.get("datSet", ""),
            "conf_rev": gcb.get("confRev", "1"),
            "app_id": "",      # filled from Communication section
            "vlan_id": "",
            "vlan_priority": "",
            "mac_address": "",
            "min_time": "",
            "max_time": "",
        })
    return gcbs


def _extract_sv_cbs(ld_elem: ET.Element, ied_name: str) -> list[dict]:
    svcbs = []
    ln0 = ld_elem.find(_tag("LN0"))
    if ln0 is None:
        return svcbs
    for svcb in ln0.iter(_tag("SampledValueControl")):
        svcbs.append({
            "name": svcb.get("name", ""),
            "desc": svcb.get("desc", ""),
            "dataset_ref": svcb.get("datSet", ""),
            "conf_rev": svcb.get("confRev", "1"),
            "smp_rate": svcb.get("smpRate", "80"),
            "smp_mod": svcb.get("smpMod", "0"),
            "asdu_num": svcb.get("nofASDU", "1"),
            "app_id": "",
            "vlan_id": "",
            "vlan_priority": "",
            "mac_address": "",
        })
    return svcbs


def _extract_datasets(ld_elem: ET.Element, ied_name: str) -> list[dict]:
    datasets = []
    # Search LN0 and all LNs
    for container in list(ld_elem.iter(_tag("LN0"))) + list(ld_elem.iter(_tag("LN"))):
        for ds in container.findall(_tag("DataSet")):
            members = []
            for fcda in ds.iter(_tag("FCDA")):
                members.append({
                    "ld_inst": fcda.get("ldInst", ""),
                    "prefix": fcda.get("prefix", ""),
                    "ln_class": fcda.get("lnClass", ""),
                    "ln_inst": fcda.get("lnInst", ""),
                    "do_name": fcda.get("doName", ""),
                    "da_name": fcda.get("daName", ""),
                    "fc": fcda.get("fc", ""),
                })
            datasets.append({
                "name": ds.get("name", ""),
                "desc": ds.get("desc", ""),
                "members": members,
            })
    return datasets


def _extract_communication(root: ET.Element) -> dict:
    """
    Extract GSE and SMV address entries from the Communication section.
    Returns dicts keyed by (ied_name, ld_inst, cb_name).
    """
    gse_map = {}
    smv_map = {}

    comm = root.find(_tag("Communication"))
    if comm is None:
        return {"gse": gse_map, "smv": smv_map}

    for subnet in comm.iter(_tag("SubNetwork")):
        for cp in subnet.iter(_tag("ConnectedAP")):
            ied_name = cp.get("iedName", "")
            ap_name = cp.get("apName", "")

            for gse in cp.iter(_tag("GSE")):
                ld_inst = gse.get("ldInst", "")
                cb_name = gse.get("cbName", "")
                addr = _parse_address(gse)
                timing = {}
                min_time = gse.find(_tag("MinTime"))
                max_time = gse.find(_tag("MaxTime"))
                if min_time is not None:
                    timing["min_time"] = min_time.text
                if max_time is not None:
                    timing["max_time"] = max_time.text
                gse_map[(ied_name, ld_inst, cb_name)] = {**addr, **timing}

            for smv in cp.iter(_tag("SMV")):
                ld_inst = smv.get("ldInst", "")
                cb_name = smv.get("cbName", "")
                addr = _parse_address(smv)
                smv_map[(ied_name, ld_inst, cb_name)] = addr

    return {"gse": gse_map, "smv": smv_map}


def _parse_address(elem: ET.Element) -> dict:
    """Extract MAC, APPID, VLAN-ID, VLAN-PRIORITY from an Address element."""
    result = {
        "mac_address": "",
        "app_id": "",
        "vlan_id": "",
        "vlan_priority": "",
    }
    addr = elem.find(_tag("Address"))
    if addr is None:
        return result
    for p in addr.iter(_tag("P")):
        ptype = p.get("type", "")
        val = (p.text or "").strip()
        if ptype == "MAC-Address":
            result["mac_address"] = val
        elif ptype == "APPID":
            result["app_id"] = val
        elif ptype == "VLAN-ID":
            result["vlan_id"] = val
        elif ptype == "VLAN-PRIORITY":
            result["vlan_priority"] = val
    return result


def _resolve_dataset_members(
    scd_path: str, ied_name: str, ld_inst: str, ds_name: str
) -> list[dict]:
    """Look up dataset members from the parsed SCD."""
    tree = ET.parse(scd_path)
    root = tree.getroot()

    for ied in root.iter(_tag("IED")):
        if ied.get("name") != ied_name:
            continue
        for ld in ied.iter(_tag("LDevice")):
            if ld.get("inst") != ld_inst:
                continue
            for container in list(ld.iter(_tag("LN0"))) + list(ld.iter(_tag("LN"))):
                for ds in container.findall(_tag("DataSet")):
                    if ds.get("name") == ds_name:
                        members = []
                        for fcda in ds.iter(_tag("FCDA")):
                            # Build a human-readable signal path
                            prefix = fcda.get("prefix", "")
                            ln_class = fcda.get("lnClass", "")
                            ln_inst = fcda.get("lnInst", "")
                            do_name = fcda.get("doName", "")
                            da_name = fcda.get("daName", "")
                            signal_path = f"{ied_name}{fcda.get('ldInst', ld_inst)}/{prefix}{ln_class}{ln_inst}.{do_name}"
                            if da_name:
                                signal_path += f".{da_name}"
                            members.append({
                                "signal_path": signal_path,
                                "ld_inst": fcda.get("ldInst", ld_inst),
                                "prefix": prefix,
                                "ln_class": ln_class,
                                "ln_inst": ln_inst,
                                "do_name": do_name,
                                "da_name": da_name,
                                "fc": fcda.get("fc", ""),
                            })
                        return members
    return []
