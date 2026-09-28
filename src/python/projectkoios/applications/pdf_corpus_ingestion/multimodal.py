"""Application policy for bounded local multimodal PDF resolution."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields

from projectkoios.ingestion import (
    OLLAMA_MULTIMODAL_PROMPT_VERSION,
    OllamaMultimodalConfiguration,
    OllamaMultimodalLimits,
    OllamaRequestOptions,
    PyMuPdfRegionRenderer,
    RegionColorMode,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class PdfCorpusMultimodalPolicy:
    """Bind deterministic selection/rendering and the expected Ollama runtime."""

    selection_warning_code: str
    native_text_character_threshold: int
    maximum_pages_per_document: int
    maximum_pages_per_tranche: int
    request_max_selections: int
    renderer_resolution_dpi: int
    renderer_color_mode: str
    renderer_max_selections: int
    renderer_max_dimension_pixels: int
    renderer_max_pixels: int
    renderer_max_raster_bytes: int
    renderer_max_total_pixels: int
    renderer_max_total_raster_bytes: int
    prompt_version: str
    expected_ollama_version: str
    model_name: str
    expected_model_digest: str
    temperature: float
    seed: int
    context_tokens: int
    output_tokens: int
    keep_alive: str
    max_image_bytes: int
    max_total_image_bytes: int
    max_pixels_per_image: int
    max_total_pixels: int
    max_prompt_bytes: int
    max_request_bytes: int
    max_metadata_response_bytes: int
    max_response_bytes: int
    max_output_bytes: int
    max_output_bytes_per_selection: int
    max_warnings_per_selection: int
    max_warning_bytes: int
    connect_timeout_seconds: float
    read_timeout_seconds: float

    def __post_init__(self) -> None:
        if self.selection_warning_code != "pdf.low_text_density":
            raise ValueError("unsupported unresolved-page selection policy")
        for name in (
            "native_text_character_threshold",
            "maximum_pages_per_document",
            "maximum_pages_per_tranche",
            "request_max_selections",
        ):
            value = getattr(self, name)
            minimum = 0 if name == "native_text_character_threshold" else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} is outside its application bound")
        if self.native_text_character_threshold > 1_000_000:
            raise ValueError("native_text_character_threshold exceeds 1000000")
        if self.maximum_pages_per_document > 256:
            raise ValueError("maximum_pages_per_document exceeds 256")
        if self.maximum_pages_per_tranche > 4096:
            raise ValueError("maximum_pages_per_tranche exceeds 4096")
        if self.request_max_selections > 16:
            raise ValueError("request_max_selections exceeds adapter hard limit")
        if self.renderer_max_selections != 1:
            raise ValueError("renderer_max_selections must be one")
        if self.prompt_version != OLLAMA_MULTIMODAL_PROMPT_VERSION:
            raise ValueError("multimodal prompt version is incompatible")
        if (
            not isinstance(self.model_name, str)
            or not self.model_name
            or len(self.model_name.encode("utf-8")) > 512
            or any(character.isspace() for character in self.model_name)
        ):
            raise ValueError("model_name must be bounded text without whitespace")
        if not isinstance(self.expected_model_digest, str):
            raise ValueError("expected_model_digest must be text")
        digest = self.expected_model_digest.removeprefix("sha256:")
        if _SHA256.fullmatch(digest) is None:
            raise ValueError("expected_model_digest must be a lowercase SHA-256")
        if (
            not isinstance(self.expected_ollama_version, str)
            or not self.expected_ollama_version
            or len(self.expected_ollama_version.encode("utf-8")) > 128
            or any(character.isspace() for character in self.expected_ollama_version)
        ):
            raise ValueError("expected_ollama_version is invalid")
        if (
            self.renderer_max_pixels > self.max_pixels_per_image
            or self.renderer_max_total_pixels > self.max_total_pixels
            or self.renderer_max_raster_bytes > self.max_image_bytes
            or self.renderer_max_total_raster_bytes > self.max_total_image_bytes
        ):
            raise ValueError("renderer limits exceed Ollama image limits")
        self.renderer()
        self.ollama_configuration("http://127.0.0.1:11434")

    @classmethod
    def create(
        cls,
        *,
        native_text_character_threshold: int,
        maximum_pages_per_document: int,
        maximum_pages_per_tranche: int,
        request_max_selections: int,
        expected_ollama_version: str,
        model_name: str,
        expected_model_digest: str,
        renderer_resolution_dpi: int = 144,
        renderer_color_mode: str = "rgb",
        renderer_max_selections: int = 1,
        renderer_max_dimension_pixels: int = 16_384,
        renderer_max_pixels: int = 3_000_000,
        renderer_max_raster_bytes: int = 10_000_000,
        renderer_max_total_pixels: int = 3_000_000,
        renderer_max_total_raster_bytes: int = 10_000_000,
        options: OllamaRequestOptions | None = None,
        limits: OllamaMultimodalLimits | None = None,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 120.0,
    ) -> PdfCorpusMultimodalPolicy:
        options = OllamaRequestOptions() if options is None else options
        limits = OllamaMultimodalLimits() if limits is None else limits
        return cls(
            selection_warning_code="pdf.low_text_density",
            native_text_character_threshold=native_text_character_threshold,
            maximum_pages_per_document=maximum_pages_per_document,
            maximum_pages_per_tranche=maximum_pages_per_tranche,
            request_max_selections=request_max_selections,
            renderer_resolution_dpi=renderer_resolution_dpi,
            renderer_color_mode=renderer_color_mode,
            renderer_max_selections=renderer_max_selections,
            renderer_max_dimension_pixels=renderer_max_dimension_pixels,
            renderer_max_pixels=renderer_max_pixels,
            renderer_max_raster_bytes=renderer_max_raster_bytes,
            renderer_max_total_pixels=renderer_max_total_pixels,
            renderer_max_total_raster_bytes=renderer_max_total_raster_bytes,
            prompt_version=OLLAMA_MULTIMODAL_PROMPT_VERSION,
            expected_ollama_version=expected_ollama_version,
            model_name=model_name,
            expected_model_digest=expected_model_digest.removeprefix("sha256:"),
            temperature=float(options.temperature),
            seed=options.seed,
            context_tokens=options.context_tokens,
            output_tokens=options.output_tokens,
            keep_alive=options.keep_alive,
            max_image_bytes=limits.max_image_bytes,
            max_total_image_bytes=limits.max_total_image_bytes,
            max_pixels_per_image=limits.max_pixels_per_image,
            max_total_pixels=limits.max_total_pixels,
            max_prompt_bytes=limits.max_prompt_bytes,
            max_request_bytes=limits.max_request_bytes,
            max_metadata_response_bytes=limits.max_metadata_response_bytes,
            max_response_bytes=limits.max_response_bytes,
            max_output_bytes=limits.max_output_bytes,
            max_output_bytes_per_selection=limits.max_output_bytes_per_selection,
            max_warnings_per_selection=limits.max_warnings_per_selection,
            max_warning_bytes=limits.max_warning_bytes,
            connect_timeout_seconds=float(connect_timeout_seconds),
            read_timeout_seconds=float(read_timeout_seconds),
        )

    def renderer(self) -> PyMuPdfRegionRenderer:
        return PyMuPdfRegionRenderer(
            resolution_dpi=self.renderer_resolution_dpi,
            color_mode=RegionColorMode(self.renderer_color_mode),
            max_selections=self.renderer_max_selections,
            max_dimension_pixels=self.renderer_max_dimension_pixels,
            max_pixels=self.renderer_max_pixels,
            max_raster_bytes=self.renderer_max_raster_bytes,
            max_total_pixels=self.renderer_max_total_pixels,
            max_total_raster_bytes=self.renderer_max_total_raster_bytes,
        )

    def ollama_configuration(self, endpoint: str) -> OllamaMultimodalConfiguration:
        options = OllamaRequestOptions(
            temperature=self.temperature,
            seed=self.seed,
            context_tokens=self.context_tokens,
            output_tokens=self.output_tokens,
            keep_alive=self.keep_alive,
        )
        limits = OllamaMultimodalLimits(
            max_selections=self.request_max_selections,
            max_image_bytes=self.max_image_bytes,
            max_total_image_bytes=self.max_total_image_bytes,
            max_pixels_per_image=self.max_pixels_per_image,
            max_total_pixels=self.max_total_pixels,
            max_prompt_bytes=self.max_prompt_bytes,
            max_request_bytes=self.max_request_bytes,
            max_metadata_response_bytes=self.max_metadata_response_bytes,
            max_response_bytes=self.max_response_bytes,
            max_output_bytes=self.max_output_bytes,
            max_output_bytes_per_selection=self.max_output_bytes_per_selection,
            max_warnings_per_selection=self.max_warnings_per_selection,
            max_warning_bytes=self.max_warning_bytes,
        )
        return OllamaMultimodalConfiguration(
            endpoint=endpoint,
            model_name=self.model_name,
            expected_model_digest=self.expected_model_digest,
            expected_ollama_version=self.expected_ollama_version,
            options=options,
            limits=limits,
            connect_timeout_seconds=self.connect_timeout_seconds,
            read_timeout_seconds=self.read_timeout_seconds,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: object) -> PdfCorpusMultimodalPolicy:
        expected = {field.name for field in fields(cls)}
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("multimodal policy fields are incomplete or unknown")
        return cls(**value)
