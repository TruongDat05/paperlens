"""Authenticate sessions and establish owner scope.

Verify a beta token against its server-side hash or verify an access
token with the integrated identity provider. Derive the owner from the
authenticated identity.

Use the server-assigned owner to authorize access to papers, caches, and
runs. The extension origin policy belongs to HTTP configuration.
"""
