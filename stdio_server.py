#!/usr/bin/env python3
"""Simple stdio MCP server for Google Ads - works directly with Claude Desktop."""

from mcp.server.fastmcp import FastMCP
import asyncio

# Import the configured tools
from standalone_server import list_accessible_customers, search, mcp

if __name__ == "__main__":
    # Run MCP server in stdio mode
    asyncio.run(mcp.run())
