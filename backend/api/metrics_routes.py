"""Prometheus-compatible metrics endpoint."""

from fastapi import APIRouter, Response

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
def prometheus_metrics():
    from backend.utils.websocket import manager
    from backend.api.system_routes import _pipeline_status

    lines = [
        "# HELP aegis_websocket_connections Active WebSocket connections",
        "# TYPE aegis_websocket_connections gauge",
        f'aegis_websocket_connections{{channel="alerts"}} {manager.get_connection_count("alerts")}',
        f'aegis_websocket_connections{{channel="status"}} {manager.get_connection_count("status")}',
        "# HELP aegis_pipeline_online Pipeline heartbeat status (1=online)",
        "# TYPE aegis_pipeline_online gauge",
        f"aegis_pipeline_online {1 if _pipeline_status.get('online') else 0}",
    ]
    body = "\n".join(lines) + "\n"
    return Response(body, media_type="text/plain; version=0.0.4")
