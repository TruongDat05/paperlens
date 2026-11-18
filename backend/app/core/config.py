"""Load and validate backend and benchmark configuration.

Build settings when FastAPI or the CLI starts. Read product settings
from configs/product_mvp.yaml. In local development, read connection
settings from the root .env using the names in .env.example. In hosted
environments, read the corresponding server environment variables.
Validate credentials for enabled providers.

The CLI loads the selected benchmark configuration and live or replay
mode. Pass the run settings to the pipeline and adapters for consistent
behavior across callers.
"""
