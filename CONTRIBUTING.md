# Contributing to IEC 61850 MCP Server

Thank you for considering contributing to this project! This guide will help you get started.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Areas Where Help Is Needed](#areas-where-help-is-needed)

---

## Code of Conduct

Be respectful and professional. We're all here to build better tooling for the OT/ICS community.

---

## How Can I Contribute?

### Reporting Bugs

**Before submitting a bug report:**
- Check the [existing issues](https://github.com/yourusername/iec61850-mcp-server/issues) to see if it's already reported
- Test with the latest version from `main` branch
- Collect diagnostic information (Python version, OS, error messages, sample SCD file if possible)

**When submitting a bug report, include:**
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Error messages (full stack traces)
- Environment details (Python version, OS, RTAC/CODESYS version if applicable)
- Sample SCD file (anonymized/sanitized if needed)

### Suggesting Features

Open a GitHub Issue with:
- **Use case:** Why is this feature needed? What problem does it solve?
- **Proposed solution:** How should it work?
- **Alternatives considered:** What other approaches did you think about?

### Contributing Code

See [Development Setup](#development-setup) and [Pull Request Process](#pull-request-process) below.

---

## Development Setup

### Prerequisites
- Python 3.10 or higher
- Git
- A text editor or IDE (VS Code recommended)

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/your-username/iec61850-mcp-server.git
   cd iec61850-mcp-server
   ```
3. Add upstream remote:
   ```bash
   git remote add upstream https://github.com/originalowner/iec61850-mcp-server.git
   ```

### Install Dependencies

```bash
# Create a virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Run Tests

```bash
python tests/test_pipeline.py
```

All tests should pass on a fresh install.

---

## Coding Standards

### Python Style

Follow [PEP 8](https://pep8.org/) with these specifics:
- **Line length:** 100 characters max
- **Indentation:** 4 spaces (no tabs)
- **Imports:** Grouped (standard library, third-party, local) with blank lines between groups
- **Type hints:** Required for function signatures
- **Docstrings:** Use Google style for all public functions

**Example:**

```python
from typing import Any

def generate_rtac_tag_mapping(
    scd_path: str,
    gcb_ref: str,
    tag_prefix: str = "",
) -> dict[str, Any]:
    """
    Generate Tag Processor mapping rows for a GOOSE control block.
    
    Args:
        scd_path: Path to the SCD file
        gcb_ref: Full GoCB reference (e.g., "PROT1LD0/LLN0$GO$GCB01")
        tag_prefix: Optional prefix for generated tag names
        
    Returns:
        Dict containing mappings list and metadata, or {"error": "..."} on failure
        
    Example:
        >>> mapping = generate_rtac_tag_mapping("bay1.scd", "PROT1LD0/LLN0$GO$GCB01", "BAY1_")
        >>> print(mapping["count"])
        5
    """
    # Implementation here
```

### Error Handling

- **Tool functions:** Return `{"error": "descriptive message"}` on failure, never raise exceptions to the MCP layer
- **Internal functions:** Can raise exceptions; they're caught by tool wrappers
- **Validation:** Always validate inputs; fail fast with clear error messages

**Example:**

```python
def parse_scd_file(path: str) -> dict[str, Any]:
    """Parse an SCD file."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        # ... parsing logic
        return {"ied_count": len(ieds), "ieds": ieds}
    except FileNotFoundError:
        return {"error": f"SCD file not found: {path}"}
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error parsing SCD: {e}"}
```

### Code Organization

```
iec61850-mcp-server/
├── server.py              # MCP server entry point; tool registration
├── tools/
│   ├── scd_parser.py      # SCD/XML parsing functions
│   ├── rtac_generator.py  # RTAC .EXP generation
│   ├── codesys_generator.py  # CODESYS ST code generation
│   └── validator.py       # Config validation functions
├── tests/
│   ├── test_pipeline.py   # End-to-end integration tests
│   └── test_*.py          # Unit tests for individual modules
├── sample_data/
│   └── *.scd              # Example SCD files for testing
└── templates/             # (Future) Jinja2 templates for code gen
```

**Adding a new tool:**

1. Implement the function in the appropriate `tools/*.py` module
2. Add it to `server.py` in `list_tools()` and `call_tool()`
3. Write tests in `tests/test_*.py`
4. Update README.md with usage example

---

## Testing Guidelines

### Test Structure

```python
def test_feature_name():
    """Test description."""
    # Arrange
    scd_path = "sample_data/test.scd"
    
    # Act
    result = my_tool_function(scd_path, "param")
    
    # Assert
    assert "error" not in result
    assert result["count"] > 0
    assert result["some_field"] == expected_value
```

### Test Data

- Use files in `sample_data/` for tests
- Keep test SCD files small (< 50 IEDs)
- Anonymize real substation data (change IED names, IP addresses, site names)

### Running Tests

```bash
# Run all tests
python tests/test_pipeline.py

# Run with verbose output
python tests/test_pipeline.py -v

# Test a specific module
python -m pytest tests/test_scd_parser.py
```

### What to Test

- **Happy path:** Does it work with valid inputs?
- **Edge cases:** Empty datasets, single-member datasets, 100+ member datasets
- **Error handling:** Missing files, malformed XML, invalid GoCB references
- **Validation:** Does the validator catch known bad configs?
- **Cross-vendor compatibility:** Test with SCD files from different tool vendors (ABB, Siemens, SEL)

---

## Pull Request Process

### Before Submitting

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Write your code** following [Coding Standards](#coding-standards)

3. **Add tests** for new functionality

4. **Run all tests** and ensure they pass:
   ```bash
   python tests/test_pipeline.py
   ```

5. **Update documentation:**
   - Add docstrings to new functions
   - Update README.md if adding a new tool or changing usage
   - Add examples to the Examples section

6. **Commit with clear messages:**
   ```bash
   git commit -m "Add get_goose_subscriptions tool for ExtRef extraction"
   ```

7. **Push to your fork:**
   ```bash
   git push origin feature/my-new-feature
   ```

### Submitting the PR

1. Go to the original repository on GitHub
2. Click "New Pull Request"
3. Select your feature branch
4. Fill out the PR template with:
   - **Description:** What does this change do?
   - **Motivation:** Why is this change needed?
   - **Testing:** How did you test it?
   - **Breaking changes:** Does this break existing functionality?

### PR Review Process

- Maintainers will review within 3-5 days
- Address review comments by pushing new commits to your branch
- Once approved, a maintainer will merge your PR

### Commit Message Guidelines

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add get_goose_subscriptions tool for ExtRef extraction
fix: handle missing confRev in GOOSE control blocks
docs: update README with CODESYS integration examples
test: add validation tests for duplicate AppIDs
refactor: extract CDC type mapping into separate function
```

---

## Areas Where Help Is Needed

### High Priority

1. **Tag Name Deduplication**  
   The RTAC generator creates duplicate tag names when multiple publishers have identical signal names. Need auto-deduplication logic with collision counters.

2. **ExtRef / Subscription Extraction**  
   Add a `get_goose_subscriptions(ied_name)` tool that extracts all `<ExtRef>` elements and maps them back to source GoCBs.

3. **Real-World SCD Testing**  
   Test with SCD files from different vendors and tool versions. Report compatibility issues or contribute sanitized samples.

4. **MCP SDK Integration**  
   Once the official `mcp` Python package is available on PyPI, update `requirements.txt` and test server startup via stdio.

### Medium Priority

5. **Sampled Values Support**  
   Implement full SV subscriber generation including MU sync configuration and sample rate handling.

6. **SCL Schema Validation**  
   Validate input SCD files against IEC 61850-6 XSD schema before parsing.

7. **Template-Based Code Generation**  
   Migrate string-based code generation to Jinja2 templates for easier customization.

8. **CODESYS Library Examples**  
   Document integration with common CODESYS IEC 61850 libraries (official CODESYS lib, vendor libs).

### Lower Priority / Future Enhancements

9. **ICD File Generation**  
   Generate ICD files (IED capability descriptions) from RTAC or CODESYS projects.

10. **Web UI**  
    Build a FastAPI + React web interface for non-Claude users.

11. **Docker Container**  
    Provide a Docker image for easier deployment.

12. **IEC 61850-90-5 Support**  
    Add routable GOOSE/SV over IP support.

---

## Questions?

- Open a [GitHub Discussion](https://github.com/yourusername/iec61850-mcp-server/discussions) for general questions
- Comment on relevant issues for specific feature discussions
- Tag maintainers in PRs if you need quick feedback

---

**Thank you for contributing to better OT/ICS automation tooling!**
