"""Module declaring the singleton MCP instance.

The singleton allows other modules to register their tools with the same MCP
server using @mcp.tool annotations, thereby 'coordinating' the bootstrapping
of the server.
"""
from mcp.server.fastmcp import FastMCP

# Creates the singleton.
mcp = FastMCP("Google Ads MCP Server")
