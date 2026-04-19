"""Connector package for web-cybersecurity source ingestion."""

from .config import ConnectorPack, load_connector_pack
from .registry import supported_sources
from .runner import collect_pack, collect_pack_from_file

__all__ = [
    "ConnectorPack",
    "collect_pack",
    "collect_pack_from_file",
    "load_connector_pack",
    "supported_sources",
]
