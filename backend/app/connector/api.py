"""Public facade of the connector module."""
from .models import Company, CompanyWatchlist, ConnectorSetting, Job, JobExtraction
from .registry import all_descriptors, can_auto_apply, get_link_connector, is_enabled, load_config
from .spi import ComplianceMode, ConnectorConfig, JobQuery

__all__ = [
    "Company", "CompanyWatchlist", "ConnectorSetting", "Job", "JobExtraction",
    "all_descriptors", "can_auto_apply", "get_link_connector", "is_enabled",
    "load_config", "ComplianceMode", "ConnectorConfig", "JobQuery",
]
