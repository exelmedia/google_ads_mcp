# Google Ads MCP Server

MCP (Model Context Protocol) server for Google Ads API. Allows AI assistants to query Google Ads data using the Google Ads API.

## Features

- **list_accessible_customers**: Get list of accessible customer accounts
- **search**: Execute GAQL queries to fetch Google Ads data
- HTTP transport compatible (FastMCP)
- Secure credential handling (base64 encoding support)

## Prerequisites

- Python 3.10+
- Google Cloud Project with Google Ads API enabled
- Google Ads Developer Token
- Service Account credentials with Google Ads API access

## Local Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```
GOOGLE_PROJECT_ID=your-project-id
GOOGLE_ADS_DEVELOPER_TOKEN=your-developer-token
GOOGLE_CREDENTIALS_HOST_PATH=./credentials.json
```

### 3. Add Credentials File

Place your Google Cloud service account credentials in `credentials.json`.

Alternatively, create `google-ads.yaml`:
```yaml
developer_token: "your-developer-token"
use_proto_plus: True
login_customer_id: "your-manager-account-id"
json_key_file_path: "./credentials.json"
```

### 4. Run Server Locally

```bash
python server.py
```

## Deployment to Elast.io

### Build Command
```
pip install --no-cache-dir -r requirements.txt
```

### Install Command
```
python -c "import sys; sys.exit(0)"
```

### Run Command
```
python server.py
```

### Environment Variables

Set these in the Elast.io dashboard:

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_PROJECT_ID` | Your Google Cloud Project ID | Yes |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Google Ads API developer token | Yes |
| `GOOGLE_CREDENTIALS_BASE64` | Base64-encoded service account JSON | Yes |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Manager account ID (if applicable) | No |

#### How to Create GOOGLE_CREDENTIALS_BASE64

```bash
base64 -i credentials.json | tr -d '\n'
```

Copy the output and paste it as the `GOOGLE_CREDENTIALS_BASE64` environment variable.

### Reverse Proxy Configuration

- **Target**: `172.17.0.1`
- **Port**: `8000`

## API Usage

### list_accessible_customers

Returns list of customer IDs accessible to the authenticated account.

```python
# Example response
["1234567890", "9876543210"]
```

### search

Execute GAQL queries against Google Ads API.

**Parameters:**
- `customer_id` (str): Customer account ID
- `query` (str): Full GAQL query, OR:
- `fields` (list): Fields to select
- `resource` (str): Resource to query from
- `conditions` (list, optional): WHERE conditions
- `orderings` (list, optional): ORDER BY clauses
- `limit` (int, optional): Result limit

**Example Query:**
```python
search(
    customer_id="1234567890",
    query="SELECT campaign.id, campaign.name FROM campaign WHERE campaign.status = 'ENABLED' LIMIT 10"
)
```

**Example with Parameters:**
```python
search(
    customer_id="1234567890",
    fields=["campaign.id", "campaign.name", "campaign.status"],
    resource="campaign",
    conditions=["campaign.status = 'ENABLED'"],
    limit=10
)
```

## Security Notes

- Never commit `.env` or `credentials.json` to version control
- Use environment variables for sensitive data in production
- For deployment, use base64-encoded credentials in `GOOGLE_CREDENTIALS_BASE64`
- Service account should have minimal required permissions

## Project Structure

```
google-ads-mcp-server/
├── ads_mcp/                      # MCP module
│   ├── __init__.py
│   └── mcp_header_interceptor.py # gRPC interceptor
├── server.py                     # Main server file
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment template
├── .gitignore                   # Git ignore rules
├── credentials.json             # Service account (not in git)
├── google-ads.yaml              # Optional config (not in git)
└── README.md                    # This file
```

## Troubleshooting

### Authentication Errors

- Verify service account has Google Ads API access
- Check developer token is valid and approved
- Ensure credentials.json is properly formatted

### No Data Returned

- Verify customer_id has data
- Check GAQL query syntax
- Ensure account has active campaigns/resources

### Import Errors

- Run `pip install -r requirements.txt`
- Check Python version is 3.10+

## Resources

- [Google Ads API Documentation](https://developers.google.com/google-ads/api/docs/start)
- [GAQL Query Language](https://developers.google.com/google-ads/api/docs/query/overview)
- [MCP Protocol](https://modelcontextprotocol.io/)
- [Original google-ads-mcp Library](https://github.com/exelmedia/google_ads_mcp)

## License

Apache 2.0
