# Vendored Libraries

This directory contains vendored copies of external libraries that are not yet available in PyPI or need modifications for the integration.

## iqua_softener

The `iqua_softener` library is vendored here temporarily until the upstream changes are merged and published to PyPI. This includes modifications for:

- Enhanced WebSocket support for real-time water flow data
- Token management and authentication improvements  
- Home Assistant specific optimizations

### Original Source
- Repository: https://github.com/arturzx/iqua-softener (fork by jmacul2)
- Original: https://github.com/arturzx/iqua-softener

### Dependencies
The vendored library requires:
- `requests` - HTTP client (included in Home Assistant)
- `PyJWT` - JWT token handling (added to manifest requirements)
- `websockets` - WebSocket client (optional, we use aiohttp instead)

### When to Remove
This vendored copy can be removed once:
1. The upstream library includes the necessary WebSocket and token management changes
2. The library is published to PyPI with version >= 2.0.0
3. The manifest.json is updated to use `"requirements": ["iqua-softener>=2.0.0"]` instead of vendoring