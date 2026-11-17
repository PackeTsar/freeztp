# Introduction
Version 1.6 is intended as the initial step for Python3 and current OS support.
- Logic refactoring is not done unless required to fix a problem.
- This version must support all external modules without modification (i.e., customized tftpy).

## Significant Updates
- String formatting converted to f-strings throughout
- Indentation converted from tab to space
- OS support temporarily reduced to Debian and Ubuntu.
    - Changed most module downloads to `apt install -y python3-[module]` (tftpy not available this way)
- Deprecated Python 2 code
    - `commands` and `os.system` replaced with `subprocess`
    - `quit()` replaced with `sys.exit()`
    - `raw_input` replaced by `input`
    - SNMP query method deprecated in current `pysnmp`. New asyncio mechanism used.
    - File handling switched to `with open()` instead of `open()...close()`
    - Removed forced encoding `.encode()` which caused string handling issues in multipe functions.
- Fixed syntax errors
    - config_factory>merge_test: `j2template.parse() --> env.parse()`
    - Unnecessary `else / elif` issues identified by linter are fixed. (Typically `return` followed by `else / elif`.)
    - Redefined built-in `dir`. Replaced with `directory` as needed.
- TFTPy
    - Main function calls updated due to rename in current version
- NetAddr / config_manager.filter_ips
    - Logic refined to fix DHCP setup issues

# Minimum Python3 Version
It's strongly recommended that 3.10 be the minimum version going forward.
- Introduces `platform.freedesktop_os_release` which can replace deprecated `platform.linux_distribution` for OS identification.
- Introduces `match...case` logic which can replace long `elif` chains

# Linting Suppression to Minimize Refactoring
Pylint was used to aid in migration. Every error has been reviewed. Errors for non-catastrphic issues were generally suppressed (e.g., better coding practices).

Linting has been intentionally suppressed for the errors listed below.
- Globally Suppressed Warnings
    - line-too-long
    - missing-docstring
    - invalid-name
    - global-statement
    - global-variable-undefined
    - too-many-lines
    - too-many-statements
    - too-many-instance-attributes
    - consider-using-join
    - consider-using-in

- Locally Suppressed Warnings (Disable placed at column 80 of each line impacted)
    - used-before-assignment
    - consider-using-dict-items
    - attribute-defined-outside-init
    - redefined-outer-name
    - bare-except
    - too-many-branches
    - too-many-return-statements
    - unused-variable
    - possibly-used-before-assignment
    - too-few-public-methods
    - too-many-public-methods
    - import-outside-toplevel
    - consider-using-in
    - broad-exception-caught
    - unidiomatic-typecheck
    - inconsistent-return-statements
