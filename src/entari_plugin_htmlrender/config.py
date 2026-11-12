"""Framework-neutral configuration for one HTMLRender composition."""

from __future__ import annotations

from enum import StrEnum
import keyword
from pathlib import Path
from typing import ClassVar
from typing_extensions import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Pydantic resolves this annotation while constructing the model.
from entari_plugin_htmlrender.graphics.models import GraphicsBackendName  # noqa: TC001
from entari_plugin_htmlrender.providers.sdk import ProviderId, validate_provider_id
from entari_plugin_htmlrender.resources.config import normalize_public_base_url
from entari_plugin_htmlrender.resources.headers import (
    validate_request_header_name,
    validate_request_header_value,
)


class RuntimeStartupPolicy(StrEnum):
    """Provider runtime initialization policy."""

    OFF = "off"
    WARMUP = "warmup"
    PROBE = "probe"


class _StrictRenderModel(BaseModel):
    """Reject misspelled keys inside the plugin-owned configuration tree."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
    )


class CacheSettings(_StrictRenderModel):
    """Sizing of the shared resource cache budget."""

    max_entries: int = Field(default=256, ge=0)
    max_bytes: int = Field(default=64 * 1024 * 1024, ge=0)
    max_resource_bytes: int = Field(default=64 * 1024 * 1024, ge=0)
    revalidate_seconds: float = Field(default=1.0, ge=0.0)


class TemplateSettings(_StrictRenderModel):
    """Sizing of the template environment cache."""

    environment_cache_max_entries: int = Field(default=64, ge=0)
    environment_compiled_cache_size: int = Field(default=256, ge=0)
    """Compiled-template cache size per Jinja environment; 0 disables it."""


class ResourceTraversalSettings(_StrictRenderModel):
    """Bounds for resolving nested template-variable resources."""

    max_nodes: int = Field(default=10_000, gt=0)
    max_depth: int = Field(default=64, ge=0)
    max_concurrency: int = Field(default=16, gt=0)


class LocalAccessSettings(_StrictRenderModel):
    """Security policy for local filesystem resource access."""

    allow_any_path: bool = Field(default=False)
    allowed_paths: list[Path] = Field(default_factory=list)

    @field_validator("allowed_paths", mode="before")
    @classmethod
    def _normalize_allowed_paths(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, (str, Path)):
            return [v]
        return v


class RemoteAccessSettings(_StrictRenderModel):
    """Security policy for remote (http/https) resource fetches."""

    allow_private_networks: bool = Field(default=False)
    allow_hosts: list[str] = Field(default_factory=list)
    deny_hosts: list[str] = Field(default_factory=list)
    max_redirects: int = Field(default=5, ge=0)
    request_timeout_seconds: float = Field(default=30.0, gt=0.0)
    max_concurrent_fetches: int = Field(default=8, gt=0)


class FilehostSettings(_StrictRenderModel):
    """Core-owned settings for the optional asset publisher adapter."""

    bind_host: str = Field(default="127.0.0.1")
    bind_port: int = Field(default=8080, ge=0, le=65535)
    cache_ttl_seconds: float = Field(default=300.0, ge=0.0)
    request_header_name: str = Field(default="X-HTMLRender-Filehost-Request")
    request_header_value: str | None = Field(default=None)
    request_header_salt: str = Field(
        default="entari-plugin-htmlrender:filehost:guard:v1"
    )
    prewarm_enabled: bool = Field(default=True)
    prewarm_max_files: int = Field(default=256, ge=0)
    prewarm_paths: list[Path] = Field(default_factory=list)
    prewarm_extensions: list[str] = Field(default_factory=list)
    public_base_url: str | None = Field(default=None)
    """Externally reachable absolute base of the hosted asset collection.

    Required whenever the selected resource strategy uses the filehost
    transport; deployment configuration mapped by the reverse proxy to the
    fixed internal mount, never derived from bind addresses, ``Host`` /
    ``Forwarded`` headers, or request context.
    """
    max_entries: int = Field(default=256, gt=0)
    max_bytes: int = Field(default=256 * 1024 * 1024, gt=0)

    @field_validator("bind_host")
    @classmethod
    def _validate_bind_host(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("filehost bind host must not be empty")
        return value

    @field_validator("request_header_name")
    @classmethod
    def _validate_request_header_name(cls, value: str) -> str:
        return validate_request_header_name(value)

    @field_validator("request_header_value")
    @classmethod
    def _validate_request_header_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_request_header_value(value)

    @field_validator("public_base_url")
    @classmethod
    def _normalize_public_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_public_base_url(value)


class ObservabilitySettings(_StrictRenderModel):
    """Which observability integrations this plugin exports to."""

    sentry: bool = Field(default=False)
    prometheus: bool = Field(default=False)


class PythonDrawingSettings(_StrictRenderModel):
    """One explicitly configured, trusted Python drawing entry point."""

    backend: GraphicsBackendName
    path: Path | None = None
    module: str | None = None
    function: str = "draw"
    reload: bool = False

    @field_validator("path")
    @classmethod
    def _python_path(cls, value: Path | None) -> Path | None:
        if value is not None and value.suffix != ".py":
            raise ValueError("drawing path must name a .py file")
        return value

    @field_validator("module", "function")
    @classmethod
    def _python_name(cls, value: str | None) -> str | None:
        if value is not None and not all(
            part.isidentifier() and not keyword.iskeyword(part)
            for part in value.split(".")
        ):
            raise ValueError("drawing module and function must be Python names")
        return value

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.path is None) == (self.module is None):
            raise ValueError("drawing requires exactly one of path or module")
        if "." in self.function:
            raise ValueError("drawing function must be a module-level name")
        return self


class GraphicsSettings(_StrictRenderModel):
    """Selection and budgets for backend-neutral graphics renderers."""

    backend: GraphicsBackendName | None = None
    backends: tuple[GraphicsBackendName, ...] = ()
    drawings: dict[str, PythonDrawingSettings] = Field(default_factory=dict)
    max_pixels: int = Field(default=16 * 1024 * 1024, gt=0)
    max_concurrency: int = Field(default=2, gt=0)
    max_commands: int = Field(default=100_000, gt=0)

    @field_validator("drawings")
    @classmethod
    def _drawing_names(
        cls, value: dict[str, PythonDrawingSettings]
    ) -> dict[str, PythonDrawingSettings]:
        if any(not name or name != name.strip() for name in value):
            raise ValueError("drawing names must be non-empty without outer whitespace")
        return value

    @field_validator("backends")
    @classmethod
    def _unique_backends(
        cls,
        value: tuple[GraphicsBackendName, ...],
    ) -> tuple[GraphicsBackendName, ...]:
        if len(set(value)) != len(value):
            raise ValueError("graphics backends must not contain duplicates")
        return value

    @model_validator(mode="after")
    def _validate_backend_selection(self) -> Self:
        if (
            self.backend is not None
            and self.backends
            and self.backend not in self.backends
        ):
            raise ValueError(
                "graphics.backend must be included in graphics.backends when both "
                "are configured"
            )
        return self


class HtmlRenderSettings(_StrictRenderModel):
    """Shared limits for provider-neutral HTML raster operations."""

    max_source_bytes: int = Field(default=64 * 1024 * 1024, gt=0)
    max_pixels: int = Field(default=16 * 1024 * 1024, gt=0)
    max_output_bytes: int = Field(default=64 * 1024 * 1024, gt=0)
    max_device_pixel_ratio: float = Field(default=4.0, gt=0)
    max_auto_height: int = Field(default=16_384, gt=0)
    max_concurrency: int = Field(default=2, gt=0)


class ResourceSettings(_StrictRenderModel):
    """Core-validated resource, cache, and security configuration."""

    cache: CacheSettings = Field(default_factory=CacheSettings)
    templates: TemplateSettings = Field(default_factory=TemplateSettings)
    traversal: ResourceTraversalSettings = Field(
        default_factory=ResourceTraversalSettings
    )
    local_access: LocalAccessSettings = Field(default_factory=LocalAccessSettings)
    remote_access: RemoteAccessSettings = Field(default_factory=RemoteAccessSettings)
    filehost: FilehostSettings = Field(default_factory=FilehostSettings)


class HtmlRenderConfig(_StrictRenderModel):
    """Complete configuration accepted by the Entari plugin."""

    provider: ProviderId | None = Field(default=None)
    startup: RuntimeStartupPolicy = Field(default=RuntimeStartupPolicy.OFF)
    provider_config: dict[str, object] = Field(default_factory=dict)
    html: HtmlRenderSettings = Field(default_factory=HtmlRenderSettings)
    graphics: GraphicsSettings = Field(default_factory=GraphicsSettings)
    resources: ResourceSettings = Field(default_factory=ResourceSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str | None) -> ProviderId | None:
        if value is None:
            return None
        return validate_provider_id(value)

    @model_validator(mode="after")
    def _validate_provider_selection(self) -> Self:
        if self.provider is not None:
            return self
        if self.provider_config:
            raise ValueError("provider_config requires a selected provider")
        if self.startup is not RuntimeStartupPolicy.OFF:
            raise ValueError("startup must be 'off' when provider is null")
        return self


__all__ = [
    "CacheSettings",
    "FilehostSettings",
    "GraphicsSettings",
    "HtmlRenderConfig",
    "HtmlRenderSettings",
    "LocalAccessSettings",
    "ObservabilitySettings",
    "PythonDrawingSettings",
    "RemoteAccessSettings",
    "ResourceSettings",
    "RuntimeStartupPolicy",
    "TemplateSettings",
]
