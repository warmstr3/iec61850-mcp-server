"""
IEC 61850 MCP Server
Parses SCD/SSD files and generates SEL RTAC .EXP project files
for GOOSE and Sampled Values configurations.
"""

import asyncio
import json
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tools.scd_parser import parse_scd_file, get_goose_control_blocks, get_sv_control_blocks
from tools.rtac_generator import generate_rtac_exp, generate_rtac_tag_mapping
from tools.validator import validate_rtac_exp, validate_goose_config
from tools.codesys_generator import generate_codesys_pou, generate_codesys_gvl

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iec61850-mcp")

app = Server("iec61850-mcp-server")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="parse_scd_file",
            description=(
                "Parse an IEC 61850 SCD/SSD/ICD file and return all IEDs, "
                "logical nodes, datasets, GOOSE control blocks, and SV control blocks."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the SCD/SSD/ICD file"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="get_goose_control_blocks",
            description=(
                "Return all GOOSE control blocks for a specific IED from a parsed SCD file, "
                "including AppID, VLAN, MAC address, dataset reference, confRev, and dataset members."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scd_path": {"type": "string", "description": "Path to SCD file"},
                    "ied_name": {"type": "string", "description": "IED name as defined in the SCD"}
                },
                "required": ["scd_path", "ied_name"]
            }
        ),
        Tool(
            name="get_sv_control_blocks",
            description=(
                "Return all Sampled Value control blocks for a specific IED, "
                "including sample rate, ASDU count, VLAN, AppID, and dataset members."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scd_path": {"type": "string", "description": "Path to SCD file"},
                    "ied_name": {"type": "string", "description": "IED name as defined in the SCD"}
                },
                "required": ["scd_path", "ied_name"]
            }
        ),
        Tool(
            name="generate_rtac_tag_mapping",
            description=(
                "Generate SEL RTAC Tag Processor mapping rows that bind GOOSE dataset members "
                "to RTAC internal tags. Returns a JSON list of tag mapping entries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scd_path": {"type": "string", "description": "Path to SCD file"},
                    "gcb_ref": {
                        "type": "string",
                        "description": "Full GoCB reference, e.g. PROT1LD0/LLN0$GO$GCB01"
                    },
                    "tag_prefix": {
                        "type": "string",
                        "description": "Prefix for generated RTAC tag names, e.g. BAY1_",
                        "default": ""
                    }
                },
                "required": ["scd_path", "gcb_ref"]
            }
        ),
        Tool(
            name="generate_rtac_exp",
            description=(
                "Generate a complete SEL RTAC .EXP project file (XML) from an SCD file. "
                "Includes GOOSE subscriber configuration, tag database entries, Tag Processor "
                "mappings, and IEC 61131-3 watchdog logic. The output file can be imported "
                "directly into AcSELerator RTAC via File > Import or the importexp CLI command."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scd_path": {
                        "type": "string",
                        "description": "Path to SCD file"
                    },
                    "rtac_ied_name": {
                        "type": "string",
                        "description": "IED name of the RTAC in the SCD (or a new name if not in SCD)"
                    },
                    "goose_subscriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of GoCB references to subscribe to, e.g. ['PROT1LD0/LLN0$GO$GCB01']"
                    },
                    "sv_subscriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of SvCB references to subscribe to (optional)",
                        "default": []
                    },
                    "tag_prefix": {
                        "type": "string",
                        "description": "Prefix for all generated tag names, e.g. 'BAY1_'",
                        "default": ""
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Where to write the .EXP file"
                    },
                    "include_watchdog": {
                        "type": "boolean",
                        "description": "Include IEC 61131-3 GOOSE staleness watchdog logic",
                        "default": True
                    }
                },
                "required": ["scd_path", "rtac_ied_name", "goose_subscriptions", "output_path"]
            }
        ),
        Tool(
            name="validate_rtac_exp",
            description=(
                "Validate a generated .EXP file against common RTAC configuration issues: "
                "tag name length/character limits, duplicate AppIDs, confRev consistency, "
                "missing quality attributes, and GOOSE MAC address format."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "exp_path": {"type": "string", "description": "Path to .EXP file to validate"},
                    "scd_path": {
                        "type": "string",
                        "description": "Optional SCD path for cross-checking confRev values"
                    }
                },
                "required": ["exp_path"]
            }
        ),
        Tool(
            name="validate_goose_config",
            description=(
                "Validate a GOOSE control block configuration from an SCD file: "
                "checks AppID uniqueness, dataset member types, retransmission timing, "
                "and VLAN/priority settings."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scd_path": {"type": "string", "description": "Path to SCD file"},
                    "gcb_ref": {"type": "string", "description": "GoCB reference to validate"}
                },
                "required": ["scd_path", "gcb_ref"]
            }
        ),
        Tool(
            name="generate_codesys_pou",
            description=(
                "Generate a CODESYS IEC 61131-3 Function Block for GOOSE subscription, "
                "ready for @codesys/mcp-toolkit. Returns the declaration and implementation "
                "strings to pass directly to set_pou_code, plus an ordered list of exact "
                "toolkit_steps (create_pou → set_pou_code → compile_project) to execute."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scd_path": {"type": "string", "description": "Path to SCD file"},
                    "goose_subscriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of GoCB references, e.g. ['PROT1LD0/LLN0$GO$GCB_PROT']"
                    },
                    "tag_prefix": {
                        "type": "string",
                        "description": "Optional prefix for all tag names, e.g. 'BAY1_'",
                        "default": ""
                    },
                    "pou_name": {
                        "type": "string",
                        "description": "Name for the generated Function Block",
                        "default": "GOOSE_Subscriber"
                    },
                    "include_watchdog": {
                        "type": "boolean",
                        "description": "Include stNum/sqNum staleness watchdog logic",
                        "default": True
                    },
                    "include_quality": {
                        "type": "boolean",
                        "description": "Include companion _Q WORD variables for IEC 61850 quality flags",
                        "default": True
                    }
                },
                "required": ["scd_path", "goose_subscriptions"]
            }
        ),
        Tool(
            name="generate_codesys_gvl",
            description=(
                "Generate a CODESYS Global Variable List (GVL) declaration for all GOOSE tags "
                "from the given subscriptions. Useful when GOOSE values need to be shared across "
                "multiple POUs. Returns declaration string and toolkit_steps for create_pou + set_pou_code."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scd_path": {"type": "string", "description": "Path to SCD file"},
                    "goose_subscriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of GoCB references to include"
                    },
                    "tag_prefix": {
                        "type": "string",
                        "description": "Optional tag name prefix",
                        "default": ""
                    },
                    "gvl_name": {
                        "type": "string",
                        "description": "Name for the Global Variable List",
                        "default": "GVL_GOOSE"
                    }
                },
                "required": ["scd_path", "goose_subscriptions"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "parse_scd_file":
            result = parse_scd_file(arguments["path"])

        elif name == "get_goose_control_blocks":
            result = get_goose_control_blocks(arguments["scd_path"], arguments["ied_name"])

        elif name == "get_sv_control_blocks":
            result = get_sv_control_blocks(arguments["scd_path"], arguments["ied_name"])

        elif name == "generate_rtac_tag_mapping":
            result = generate_rtac_tag_mapping(
                arguments["scd_path"],
                arguments["gcb_ref"],
                arguments.get("tag_prefix", "")
            )

        elif name == "generate_rtac_exp":
            result = generate_rtac_exp(
                scd_path=arguments["scd_path"],
                rtac_ied_name=arguments["rtac_ied_name"],
                goose_subscriptions=arguments["goose_subscriptions"],
                sv_subscriptions=arguments.get("sv_subscriptions", []),
                tag_prefix=arguments.get("tag_prefix", ""),
                output_path=arguments["output_path"],
                include_watchdog=arguments.get("include_watchdog", True)
            )

        elif name == "validate_rtac_exp":
            result = validate_rtac_exp(
                arguments["exp_path"],
                arguments.get("scd_path")
            )

        elif name == "validate_goose_config":
            result = validate_goose_config(arguments["scd_path"], arguments["gcb_ref"])

        elif name == "generate_codesys_pou":
            result = generate_codesys_pou(
                scd_path=arguments["scd_path"],
                goose_subscriptions=arguments["goose_subscriptions"],
                tag_prefix=arguments.get("tag_prefix", ""),
                pou_name=arguments.get("pou_name", "GOOSE_Subscriber"),
                include_watchdog=arguments.get("include_watchdog", True),
                include_quality=arguments.get("include_quality", True),
            )

        elif name == "generate_codesys_gvl":
            result = generate_codesys_gvl(
                scd_path=arguments["scd_path"],
                goose_subscriptions=arguments["goose_subscriptions"],
                tag_prefix=arguments.get("tag_prefix", ""),
                gvl_name=arguments.get("gvl_name", "GVL_GOOSE"),
            )

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
