#!/usr/bin/env python3
"""Standalone HTTP server wrapper for Google Ads MCP - no package installation needed."""

import asyncio
import json
import os
import sys
import base64
import tempfile
import logging
import re
from typing import Any, Dict, List
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import proto

import google.auth
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.v21.services.types.customer_service import ListAccessibleCustomersResponse
from google.ads.googleads.util import get_nested_attr
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import interceptor
from ads_mcp.mcp_header_interceptor import MCPHeaderInterceptor

# Create MCP instance
mcp = FastMCP("Google Ads MCP Server")

# Read-only scope for Google Ads API
_READ_ONLY_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"

# Global client instance
_googleads_client = None


def _setup_credentials_from_base64():
    """Setup credentials from base64 encoded environment variable."""
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
    if creds_b64 and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            creds_json = base64.b64decode(creds_b64).decode('utf-8')
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                f.write(creds_json)
                temp_path = f.name
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_path
            logger.info("Credentials set from GOOGLE_CREDENTIALS_BASE64")
            return True
        except Exception as e:
            logger.error(f"Failed to setup credentials from base64: {e}")
            return False
    return False


def _create_credentials():
    """Returns Application Default Credentials with read-only scope."""
    (credentials, _) = google.auth.default(scopes=[_READ_ONLY_ADS_SCOPE])
    return credentials


def _get_developer_token() -> str:
    """Returns the developer token from environment."""
    dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    if dev_token is None:
        raise ValueError("GOOGLE_ADS_DEVELOPER_TOKEN environment variable not set.")
    return dev_token


def _get_login_customer_id() -> str:
    """Returns login customer id from environment."""
    return os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")


def _get_googleads_client() -> GoogleAdsClient:
    if _setup_credentials_from_base64():
        logger.info("Using credentials from GOOGLE_CREDENTIALS_BASE64")
        client = GoogleAdsClient(
            credentials=_create_credentials(),
            developer_token=_get_developer_token(),
            login_customer_id=_get_login_customer_id()
        )
        return client
    
    yaml_path = os.environ.get('GOOGLE_ADS_YAML_PATH', 'google-ads.yaml')
    if os.path.exists(yaml_path):
        logger.info(f"Loading Google Ads client from {yaml_path}")
        client = GoogleAdsClient.load_from_storage(yaml_path)
        return client
    
    logger.info("Loading Google Ads client from Application Default Credentials")
    client = GoogleAdsClient(
        credentials=_create_credentials(),
        developer_token=_get_developer_token(),
        login_customer_id=_get_login_customer_id()
    )
    return client


def get_googleads_service(serviceName: str):
    global _googleads_client
    if _googleads_client is None:
        _googleads_client = _get_googleads_client()
    return _googleads_client.get_service(
        serviceName, interceptors=[MCPHeaderInterceptor()]
    )


def _ensure_serializable(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable types."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, proto.Enum):
        return obj.name
    elif hasattr(obj, '_pb'):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: _ensure_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_ensure_serializable(item) for item in obj]
    else:
        return str(obj)


def format_output_value(value: Any) -> Any:
    """Format a single value for safe JSON serialization."""
    try:
        return _ensure_serializable(value)
    except Exception as e:
        logger.warning(f"Error formatting value {type(value)}: {e}")
        return str(value)


def format_output_row(row: proto.Message, attributes):
    """Format a row for safe JSON serialization."""
    result = {}
    for attr in attributes:
        try:
            value = get_nested_attr(row, attr)
            result[attr] = format_output_value(value)
        except Exception as e:
            logger.warning(f"Error getting attribute {attr}: {e}")
            result[attr] = f"Error: {str(e)}"
    
    try:
        json.dumps(result)
        return result
    except Exception as e:
        logger.error(f"Row serialization failed: {e}")
        return {attr: str(getattr(row, attr.split('.')[0], 'N/A')) for attr in attributes}


@mcp.tool()
def list_accessible_customers() -> List[str]:
    """Returns ids of customers directly accessible by the user authenticating the call."""
    ga_service = get_googleads_service("CustomerService")
    accessible_customers: ListAccessibleCustomersResponse = (
        ga_service.list_accessible_customers()
    )
    return [
        cust_rn.removeprefix("customers/")
        for cust_rn in accessible_customers.resource_names
    ]


@mcp.tool()
def search(
    customer_id: str,
    fields: List[str] = None,
    resource: str = None,
    conditions: List[str] = None,
    orderings: List[str] = None,
    limit: int = None,
    query: str = None,
) -> List[Dict[str, Any]]:
    """Fetches data from the Google Ads API using the search method"""
    if query:
        query = query.strip()
        select_match = re.search(r'SELECT\s+(.+?)\s+FROM\s+(\w+)', query, re.IGNORECASE)
        if select_match:
            fields = [field.strip() for field in select_match.group(1).split(',')]
            resource = select_match.group(2)
            
            if not conditions:
                where_match = re.search(r'WHERE\s+(.+?)(?:\s+ORDER\s+BY|\s+LIMIT|$)', query, re.IGNORECASE)
                if where_match:
                    conditions = [where_match.group(1)]
            
            if not orderings:
                order_match = re.search(r'ORDER\s+BY\s+(.+?)(?:\s+LIMIT|$)', query, re.IGNORECASE)
                if order_match:
                    orderings = [order_match.group(1)]
            
            if not limit:
                limit_match = re.search(r'LIMIT\s+(\d+)', query, re.IGNORECASE)
                if limit_match:
                    limit = int(limit_match.group(1))
        else:
            raise ValueError("Invalid GAQL query: missing SELECT and FROM clauses")
    
    if not fields or not resource:
        raise ValueError("Either 'query' parameter or both 'fields' and 'resource' parameters are required")

    ga_service = get_googleads_service("GoogleAdsService")
    query_parts = [f"SELECT {','.join(fields)} FROM {resource}"]

    if conditions:
        query_parts.append(f" WHERE {' AND '.join(conditions)}")
    if orderings:
        query_parts.append(f" ORDER BY {','.join(orderings)}")
    if limit:
        query_parts.append(f" LIMIT {limit}")

    query = "".join(query_parts)
    logger.info(f"Google Ads MCP search query: {query}")

    query_result = ga_service.search_stream(customer_id=customer_id, query=query)
    final_output: List = []
    for batch in query_result:
        for row in batch.results:
            final_output.append(format_output_row(row, batch.field_mask.paths))
    return final_output


# FastAPI app
app = FastAPI(title="Google Ads MCP HTTP Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "server": "Google Ads MCP Server",
        "version": "1.0.0",
        "transport": "http"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/message")
async def message_endpoint(request: Request):
    """REST endpoint for MCP messages."""
    try:
        body = await request.json()
        result = await process_mcp_request(body)
        return result
    except Exception as e:
        return {
            "error": str(e),
            "type": type(e).__name__
        }, 500


async def process_mcp_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Process an MCP request and return the result."""
    method = request.get("method")
    
    if method == "tools/list":
        tools = []
        for name, tool_func in mcp._tool_manager._tools.items():
            tools.append({
                "name": name,
                "description": tool_func.__doc__ or "",
                "inputSchema": getattr(tool_func, "_mcp_input_schema", {})
            })
        return {"tools": tools}
    
    elif method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name not in mcp._tool_manager._tools:
            return {
                "error": f"Tool '{tool_name}' not found",
                "isError": True
            }
        
        tool_func = mcp._tool_manager._tools[tool_name]
        
        try:
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**arguments)
            else:
                result = tool_func(**arguments)
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2) if not isinstance(result, str) else result
                    }
                ]
            }
        except Exception as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error calling tool: {str(e)}"
                    }
                ],
                "isError": True
            }
    
    elif method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "Google Ads MCP Server",
                "version": "1.0.0"
            }
        }
    
    else:
        return {
            "error": f"Unknown method: {method}",
            "isError": True
        }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3030))
    
    print(f"🚀 Google Ads MCP HTTP Server starting on 0.0.0.0:{port}")
    print(f"📊 Registered tools: {list(mcp._tool_manager._tools.keys())}")
    print(f"🔑 Required env vars: GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_PROJECT_ID")
    
    uvicorn.run(app, host="0.0.0.0", port=port)
