#!/usr/bin/env python3
"""Google Ads MCP Server - HTTP transport compatible implementation"""

import os
import base64
import json
import tempfile
import logging
from typing import Any, List, Dict
import proto
import re

import google.auth
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.v21.services.services.google_ads_service import GoogleAdsServiceClient
from google.ads.googleads.v21.services.types.customer_service import ListAccessibleCustomersResponse
from google.ads.googleads.util import get_nested_attr
from dotenv import load_dotenv

from fastmcp import FastMCP
from ads_mcp.mcp_header_interceptor import MCPHeaderInterceptor

# Load environment variables
load_dotenv()

# Initialize server
mcp = FastMCP("Google Ads MCP Server")

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Read-only scope for Google Ads API
_READ_ONLY_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"

# Global client instance
_googleads_client = None


def _setup_credentials_from_base64():
    """Setup credentials from base64 encoded environment variable."""
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
    if creds_b64 and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            # Decode base64 and write to temporary file
            creds_json = base64.b64decode(creds_b64).decode('utf-8')
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                f.write(creds_json)
                temp_path = f.name
            
            # Set environment variable for Google Auth
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_path
            logger.info(f"Credentials set from GOOGLE_CREDENTIALS_BASE64")
            return True
        except Exception as e:
            logger.error(f"Failed to setup credentials from base64: {e}")
            return False
    return False


def _create_credentials() -> google.auth.credentials.Credentials:
    """Returns Application Default Credentials with read-only scope."""
    (credentials, _) = google.auth.default(scopes=[_READ_ONLY_ADS_SCOPE])
    return credentials


def _get_developer_token() -> str:
    """Returns the developer token from the environment variable GOOGLE_ADS_DEVELOPER_TOKEN."""
    dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    if dev_token is None:
        raise ValueError("GOOGLE_ADS_DEVELOPER_TOKEN environment variable not set.")
    return dev_token


def _get_login_customer_id() -> str:
    """Returns login customer id, if set, from the environment variable GOOGLE_ADS_LOGIN_CUSTOMER_ID."""
    return os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")


def _get_googleads_client() -> GoogleAdsClient:
    # Setup credentials from base64 if available
    _setup_credentials_from_base64()
    
    # Try to load from google-ads.yaml if exists
    yaml_path = os.environ.get('GOOGLE_ADS_YAML_PATH', 'google-ads.yaml')
    if os.path.exists(yaml_path):
        logger.info(f"Loading Google Ads client from {yaml_path}")
        client = GoogleAdsClient.load_from_storage(yaml_path)
        return client
    
    # Fallback to environment variables
    logger.info("Loading Google Ads client from environment variables")
    client = GoogleAdsClient(
        credentials=_create_credentials(),
        developer_token=_get_developer_token(),
        login_customer_id=_get_login_customer_id()
    )
    return client


def get_googleads_service(serviceName: str) -> GoogleAdsServiceClient:
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
    elif hasattr(obj, '_pb'):  # Protocol Buffer objects
        return str(obj)
    elif isinstance(obj, dict):
        return {key: _ensure_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_ensure_serializable(item) for item in obj]
    else:
        # Fallback to string conversion for any other type
        return str(obj)


def format_output_value(value: Any) -> Any:
    """Format a single value for safe JSON serialization."""
    try:
        return _ensure_serializable(value)
    except Exception as e:
        logger.warning(f"Error formatting value {type(value)}: {e}")
        return str(value)


def format_output_row(row: proto.Message, attributes):
    """Format a row for safe JSON serialization, avoiding protobuf errors."""
    result = {}
    for attr in attributes:
        try:
            value = get_nested_attr(row, attr)
            result[attr] = format_output_value(value)
        except Exception as e:
            logger.warning(f"Error getting attribute {attr}: {e}")
            result[attr] = f"Error: {str(e)}"
    
    # Final safety check - ensure entire result is serializable
    try:
        json.dumps(result)  # Test serialization
        return result
    except Exception as e:
        logger.error(f"Row serialization failed: {e}")
        # Return a safe fallback
        return {attr: str(getattr(row, attr.split('.')[0], 'N/A')) for attr in attributes}


@mcp.tool()
def list_accessible_customers() -> List[str]:
    """Returns ids of customers directly accessible by the user authenticating the call."""
    ga_service = get_googleads_service("CustomerService")
    accessible_customers: ListAccessibleCustomersResponse = (
        ga_service.list_accessible_customers()
    )
    # remove customer/ from the start of each resource
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
    """Fetches data from the Google Ads API using the search method

    Args:
        customer_id: The id of the customer
        fields: The fields to fetch (optional if query provided)
        resource: The resource to return fields from (optional if query provided)
        conditions: List of conditions to filter the data, combined using AND clauses
        orderings: How the data is ordered
        limit: The maximum number of rows to return
        query: Full GAQL query (alternative to fields/resource parameters)
    """
    # Handle query parameter for Claude.ai compatibility
    if query:
        query = query.strip()
        
        # Extract SELECT fields and FROM resource
        select_match = re.search(r'SELECT\s+(.+?)\s+FROM\s+(\w+)', query, re.IGNORECASE)
        if select_match:
            fields = [field.strip() for field in select_match.group(1).split(',')]
            resource = select_match.group(2)
            
            # Parse WHERE conditions
            if not conditions:
                where_match = re.search(r'WHERE\s+(.+?)(?:\s+ORDER\s+BY|\s+LIMIT|$)', query, re.IGNORECASE)
                if where_match:
                    conditions = [where_match.group(1)]
            
            # Parse ORDER BY
            if not orderings:
                order_match = re.search(r'ORDER\s+BY\s+(.+?)(?:\s+LIMIT|$)', query, re.IGNORECASE)
                if order_match:
                    orderings = [order_match.group(1)]
            
            # Parse LIMIT
            if not limit:
                limit_match = re.search(r'LIMIT\s+(\d+)', query, re.IGNORECASE)
                if limit_match:
                    limit = int(limit_match.group(1))
        else:
            raise ValueError("Invalid GAQL query: missing SELECT and FROM clauses")
    
    # Validate required parameters
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

    query_result = ga_service.search_stream(
        customer_id=customer_id, query=query
    )

    final_output: List = []
    for batch in query_result:
        for row in batch.results:
            final_output.append(
                format_output_row(row, batch.field_mask.paths)
            )
    return final_output


def main():
    """Main entry point"""
    print("🚀 Google Ads MCP Server starting...")
    print(f"📊 Available tools: search, list_accessible_customers")
    print(f"🔑 Required env vars: GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_PROJECT_ID")
    print(f"🏃 Running server...")
    
    # Force SSE transport for deployment (Elast.io)
    import sys
    if '--transport' not in sys.argv:
        sys.argv.extend(['--transport', 'sse'])
    
    mcp.run()


if __name__ == "__main__":
    main()
