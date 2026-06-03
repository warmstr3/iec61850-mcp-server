# iec61850-mcp-server
# IEC 61850 MCP Server

> **Parse IEC 61850 substation configuration files and generate SEL RTAC projects and CODESYS PLC code using AI assistance**

An MCP (Model Context Protocol) server that bridges IEC 61850 substation automation with AI-powered workflows. Parse SCD/SSD files, generate SEL RTAC `.EXP` project files, create CODESYS IEC 61131-3 code for GOOSE/Sampled Values subscribers, and validate configurations — all through natural language prompts to Claude.

---

## Why This Exists

Configuring IEC 61850 GOOSE and Sampled Values in RTACs and PLCs is tedious and error-prone:
- Manually transcribing dataset members from SCD files into RTAC tag databases
- Writing boilerplate IEC 61131-3 code for GOOSE subscriber logic
- Keeping confRev values synchronized between publishers and subscribers
- Catching duplicate AppIDs, MAC address conflicts, and tag name collisions

This MCP server automates the entire pipeline. Give Claude an SCD file and a prompt like *"Generate an RTAC project that subscribes to all GOOSE from PROT1 and PROT2, prefix tags with BAY1_, include a staleness watchdog"* — and get a validated, ready-to-import `.EXP` file in seconds.

---

## Features

### SCD/SSD/ICD Parsing
- Extract all IEDs, logical nodes, datasets, GOOSE control blocks (GoCBs), and Sampled Value control blocks (SvCBs)
- Resolve communication addresses (AppID, MAC, VLAN) from the `<Communication>` section
- Map dataset members to full IEC 61850 signal paths

### SEL RTAC `.EXP` Generation
- Complete AcSELerator RTAC project files ready for import
- IEC 61850 GOOSE subscriber configuration (AppID, MAC, VLAN, confRev)
- Tag database with CDC-aware typing (SPS → `SPS`, DPS → `DPS`, MV → `MV`, etc.)
- Tag Processor mappings binding GOOSE dataset members to RTAC internal tags
- IEC 61131-3 Structured Text watchdog function block:
  - `stNum`/`sqNum` change detection
  - Staleness alarm (no GOOSE retransmission within `MaxTime`)
  - Communication failure alarm (extended timeout)

### CODESYS IEC 61131-3 Code Generation
- Function Block declarations and implementations for GOOSE subscription
- Global Variable Lists (GVLs) for cross-POU tag sharing
- CDC-to-ST type mapping (`SPS` → `BOOL`, `DPS` → `BYTE`, `MV` → `REAL`)
- Quality flag companion variables (`_Q : WORD` per signal)
- Ready for `@codesys/mcp-toolkit` integration (direct `set_pou_code` calls)

### Validation
- confRev consistency checks (EXP vs SCD)
- Duplicate AppID detection
- MAC address format validation (IEC 61850-8-1 multicast range)
- RTAC tag name constraints (length, character rules)
- Dataset member type validation
- Missing quality attribute warnings on protection signals

---

## Installation

### Prerequisites
- **Python 3.10+**
- **Claude Desktop** or **Claude CLI** (for MCP client)
- **Optional:** CODESYS V3.5 + `@codesys/mcp-toolkit` (for CODESYS integration)
- **Optional:** SEL AcSELerator RTAC (to import generated `.EXP` files)

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/iec61850-mcp-server.git
   cd iec61850-mcp-server
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   
   > ⚠️ **Note:** The `mcp` Python SDK is not yet available on PyPI. You'll need to install it manually or wait for the official release. For now, the server can be tested using the `tests/test_pipeline.py` script which exercises all tools without requiring the MCP transport layer.

3. **Test the installation:**
   ```bash
   python tests/test_pipeline.py
   ```
   
   You should see all tests pass with output showing parsed IEDs, generated RTAC tags, and validation results.

---

## Configuration

### Claude Desktop

Add to your Claude Desktop config file (`%LOCALAPPDATA%\AnthropicClaude\LocalState\mcp.json` on Windows, `~/Library/Application Support/AnthropicClaude/LocalState/mcp.json` on macOS):

```json
{
  "mcpServers": {
    "iec61850": {
      "command": "python",
      "args": ["/path/to/iec61850-mcp-server/server.py"]
    }
  }
}
```

### Claude CLI

Create a `.mcp.json` in your project directory:

```json
{
  "mcpServers": {
    "iec61850": {
      "command": "python",
      "args": ["./server.py"]
    }
  }
}
```

### With CODESYS MCP Toolkit

For the full CODESYS integration, add both servers:

```json
{
  "mcpServers": {
    "iec61850": {
      "command": "python",
      "args": ["/path/to/iec61850-mcp-server/server.py"]
    },
    "codesys": {
      "command": "codesys-mcp-tool",
      "args": [
        "--codesys-path", "C:\\Program Files\\CODESYS 3.5.22.20\\CODESYS\\Common\\CODESYS.exe",
        "--codesys-profile", "CODESYS V3.5 SP22 Patch 3"
      ]
    }
  }
}
```

---

## Usage Examples

### Parse an SCD File

> *"Parse the SCD file at `/data/substation1.scd` and show me all GOOSE control blocks"*

Claude will call `parse_scd_file` and `get_goose_control_blocks` to extract:
- IED names and logical devices
- GoCB names, datasets, AppIDs, MAC addresses, confRev values
- Dataset members with full signal paths

### Generate an RTAC .EXP File

> *"Generate an SEL RTAC project for IED `RTAC1`. Subscribe to GOOSE from `PROT1LD0/LLN0$GO$GCB_PROT` and `PROT2LD0/LLN0$GO$GCB_BUS`. Prefix all tags with `BAY1_`. Include a staleness watchdog. Save to `/output/RTAC1_Bay1.exp`."*

Claude will:
1. Parse the SCD to resolve GoCB configurations
2. Generate tag mappings with CDC-aware types
3. Create the complete `.EXP` XML file
4. Validate for confRev consistency and AppID conflicts

**Import into AcSELerator RTAC:**
- GUI: `File → Import Project`
- CLI: `AcRtacCmd importexp -p "MyProject" -f RTAC1_Bay1.exp`

### Generate CODESYS Function Block Code

> *"Generate a CODESYS Function Block named `FB_GOOSE_Bay1` that subscribes to `PROT1LD0/LLN0$GO$GCB_PROT`. Include quality flags and a watchdog. Show me the declaration and implementation."*

Claude will call `generate_codesys_pou` and return:
- `declaration`: Full VAR blocks ready for `set_pou_code`
- `implementation`: ST body with watchdog logic
- `toolkit_steps`: Ordered list of `@codesys/mcp-toolkit` calls to execute

**With CODESYS MCP toolkit connected:**

> *"Generate the CODESYS FB, then create it in my project at `C:\Projects\Bay1.project` and compile."*

Claude will:
1. Generate the code (iec61850 server)
2. Call `create_pou` (codesys server)
3. Call `set_pou_code` with declaration and implementation
4. Call `compile_project` and report any errors

### Validate a Configuration

> *"Validate the GOOSE config for `PROT1LD0/LLN0$GO$GCB_PROT` in `/data/substation1.scd`"*

Claude will check:
- AppID uniqueness and range (0x0000–0x3FFF)
- MAC address format (IEC 61850-8-1 multicast range)
- Dataset member count and types
- Retransmission timing sanity (MinTime, MaxTime)

---

## Available Tools

| Tool | Description |
|------|-------------|
| `parse_scd_file` | Parse an IEC 61850 SCD/SSD/ICD file and return all IEDs, logical nodes, datasets, GoCBs, and SvCBs |
| `get_goose_control_blocks` | Get all GOOSE control blocks for a specific IED with communication addresses and dataset members |
| `get_sv_control_blocks` | Get all Sampled Value control blocks for a specific IED |
| `generate_rtac_tag_mapping` | Generate Tag Processor mapping rows for a GOOSE control block |
| `generate_rtac_exp` | Generate a complete SEL RTAC `.EXP` project file from an SCD |
| `validate_rtac_exp` | Validate an `.EXP` file against RTAC constraints and cross-check with SCD |
| `validate_goose_config` | Validate a GOOSE control block configuration in an SCD file |
| `generate_codesys_pou` | Generate CODESYS Function Block code for GOOSE subscription |
| `generate_codesys_gvl` | Generate a CODESYS Global Variable List for GOOSE tags |

---

## Architecture

```
┌─────────────────────┐
│   Claude (AI)       │
│   Natural language  │
│   prompts           │
└──────────┬──────────┘
           │ MCP (JSON-RPC over stdio)
           │
┌──────────▼──────────────────────────────────────────┐
│  IEC 61850 MCP Server (Python)                      │
│                                                      │
│  ┌────────────────┐  ┌──────────────────┐          │
│  │ SCD Parser     │  │ RTAC Generator   │          │
│  │ (XML → dicts)  │  │ (dicts → .EXP)   │          │
│  └────────────────┘  └──────────────────┘          │
│                                                      │
│  ┌────────────────┐  ┌──────────────────┐          │
│  │ CODESYS Gen    │  │ Validator        │          │
│  │ (dicts → ST)   │  │ (confRev, AppID) │          │
│  └────────────────┘  └──────────────────┘          │
└─────────────────────────────────────────────────────┘
           │
           │ (Optional integration)
           │
┌──────────▼──────────────────────────────────────────┐
│  @codesys/mcp-toolkit (Node.js)                     │
│  - create_pou, set_pou_code, compile_project        │
│  - Direct CODESYS scripting engine integration      │
└─────────────────────────────────────────────────────┘
```

The server is stateless — each tool call is independent. The XML parsing uses Python's built-in `xml.etree.ElementTree` (no heavy dependencies). Code generation uses string templates (Jinja2 planned for future versions).

---

## Known Limitations

1. **`.EXP` XML Schema:**  
   The SEL RTAC `.EXP` format is reverse-engineered from AcSELerator exports. It works for tested RTAC firmware versions (SEL-3555, SEL-3530 with firmware 3.x/4.x), but may need adjustments for other models or versions. Always validate imported projects in AcSELerator before deployment.

2. **GOOSE Dataset Read Placeholders:**  
   The CODESYS Function Block implementation generates comment placeholders for reading GOOSE dataset members. You must replace these with actual library calls (CODESYS IEC 61850 library, SysSocket + manual decode, or RTAC bridge). This is intentional — the correct approach depends on your library availability.

3. **Sampled Values:**  
   SV subscriber generation creates a placeholder config block in the `.EXP` file with a note that MU sync (PTP/IEEE 1588) configuration is required. Full SV automation is planned but not yet implemented.

4. **Tag Name Deduplication:**  
   If multiple publishers have identically-named signals (e.g., `PROT1` and `PROT2` both publish `PDIF1.Op.general`), the generator will create duplicate tag names. The validator catches this, but the generator doesn't auto-deduplicate yet. Workaround: use different tag prefixes per publisher or manually rename in the generated `.EXP`.

5. **GOOSE Subscriptions Extraction:**  
   The parser doesn't yet extract `<ExtRef>` elements from subscriber IEDs. A `get_goose_subscriptions()` tool to map publisher → subscriber relationships is planned.

6. **MCP Python SDK:**  
   The `mcp` package is not yet available on PyPI. This server's `server.py` expects the MCP SDK to be installed separately. Until the official release, the tool logic can be tested via `tests/test_pipeline.py`.

---

## Roadmap

- [ ] Add `get_goose_subscriptions()` tool (extract `<ExtRef>` mappings)
- [ ] Implement tag name deduplication in RTAC generator
- [ ] Full Sampled Values subscriber support (MU sync config)
- [ ] Template-based code generation (Jinja2) for easier customization
- [ ] SCL schema validation (against IEC 61850-6 XSD)
- [ ] ICD file generation (publish IED capabilities back to SCD)
- [ ] Support for IEC 61850-90-5 (routable GOOSE/SV over IP)
- [ ] Web UI for non-Claude users (FastAPI + React)
- [ ] Docker container for easier deployment

---

## Contributing

Contributions are welcome! This project fills a real gap in the OT/ICS automation space, and there's plenty of room for improvement.

### How to Contribute

1. **Fork the repository** and create a feature branch
2. **Write tests** for new tools or generators (`tests/test_*.py`)
3. **Follow the existing code style:**
   - Tool functions return `dict[str, Any]` with `"error"` key on failure
   - Generators yield structured output (lists/dicts), not formatted strings
   - Validators return `{"status": "PASS"|"FAIL", "errors": [...], "warnings": [...]}`
4. **Update documentation** (docstrings, README examples)
5. **Submit a pull request** with a clear description of what you've added

### Areas Where Help Is Needed

- **Testing with real SCD files** from different vendors (ABB, Siemens, GE, SEL)
- **RTAC firmware compatibility testing** (SEL-3555, SEL-3530, SEL-3505)
- **CODESYS library integration examples** (official IEC 61850 lib, vendor-specific libs)
- **Performance optimization** for large SCD files (1000+ IEDs)
- **Error message improvements** (more actionable diagnostics)
- **Additional output formats** (other RTAC/PLC vendors beyond SEL)

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

You are free to use, modify, and distribute this software for commercial or non-commercial purposes. Attribution is appreciated but not required.

---

## Acknowledgments

- Built with assistance from Claude (Anthropic) using the Model Context Protocol
- Inspired by the need for better tooling in substation automation and OT/ICS security
- Thanks to the open-source community for `@codesys/mcp-toolkit` and IEC 61850 standardization efforts
- Sample SCD files follow IEC 61850-6 (SCL) structure; tested against IEC 61850-8-1 (GOOSE/SV) specifications

---

## Support

- **Issues:** Report bugs or request features via [GitHub Issues](https://github.com/yourusername/iec61850-mcp-server/issues)
- **Discussions:** Ask questions or share use cases in [GitHub Discussions](https://github.com/yourusername/iec61850-mcp-server/discussions)
- **Security:** For security vulnerabilities, email [your-email@example.com] (do not open public issues)

---

## Related Projects

- [`@codesys/mcp-toolkit`](https://github.com/johannesPettersson80/codesys-mcp-toolkit) — MCP server for CODESYS V3 automation
- [`libIEC61850`](https://github.com/mz-automation/libiec61850) — Open-source IEC 61850 client/server library (C)
- [`rapid61850`](https://github.com/stevenblair/rapid61850) — Lightweight GOOSE/SV code generator from SCD files (C/C++)
- [Model Context Protocol](https://modelcontextprotocol.io) — Protocol specification for AI-tool integration

---

**Built for protection engineers, SCADA integrators, and anyone tired of manually transcribing SCD files.**
