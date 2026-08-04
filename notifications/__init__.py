"""
notifications module — telegram bot & discord webhook alerts
dossier completion, extraction status, pool health, errors
"""

from .alerts import AlertManager, AlertLevel, Alert

__all__ = ["AlertManager", "AlertLevel", "Alert"]