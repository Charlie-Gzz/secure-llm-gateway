from gateway.config import Policy, Settings
from gateway.upstreams.base import Upstream, UpstreamError, UpstreamResult
from gateway.upstreams.mock import MockUpstream


def build_upstream(settings: Settings, policy: Policy) -> Upstream:
    """Pick the upstream from settings; fall back to mock when no API key is configured."""
    if settings.upstream == "anthropic" and settings.anthropic_api_key:
        from gateway.upstreams.anthropic_upstream import AnthropicUpstream

        return AnthropicUpstream(settings.anthropic_api_key, policy.upstream)
    return MockUpstream(latency_ms=settings.mock_latency_ms)


__all__ = ["Upstream", "UpstreamError", "UpstreamResult", "MockUpstream", "build_upstream"]
