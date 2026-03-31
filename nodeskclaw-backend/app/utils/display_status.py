"""Compute a unified display_status from instance status + health_status."""


def compute_display_status(status: str, health_status: str = "unknown") -> str:
    if status == "running":
        return {"healthy": "ready", "unhealthy": "unreachable"}.get(health_status, "checking")
    return {
        "creating": "preparing", "pending": "preparing", "deploying": "preparing",
        "restarting": "restarting", "updating": "updating",
        "learning": "learning", "failed": "error", "deleting": "leaving",
    }.get(status, status)
