"""Setup configuration for Google Ads MCP Server."""

from setuptools import setup, find_packages

setup(
    name="google-ads-mcp-server",
    version="1.0.0",
    description="MCP Server for Google Ads API",
    packages=find_packages(),
    install_requires=[
        "google-ads>=28.0.0",
        "google-auth>=2.40,<3.0",
        "mcp[cli]>=1.2.0",
        "fastapi>=0.115.0",
        "uvicorn>=0.32.0",
        "python-dotenv>=1.0.0",
    ],
    python_requires=">=3.10",
)
