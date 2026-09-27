"""Per-job conversion options chosen by the user on top of a preset."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SubtitleMode = Literal["none", "soft", "burn"]
Speed = Literal["fast", "balanced", "quality"]
# "auto" follows the global GPU setting; "cpu"/"gpu" pin the choice for one file
Accel = Literal["auto", "cpu", "gpu"]


class SubtitleStyle(BaseModel):
    """Appearance of burned-in text subtitles (maps to an ASS force_style)."""

    model_config = ConfigDict(extra="forbid")

    font: str = Field("Arial", pattern=r"^[\w .\-]{1,64}$")
    size: int = Field(22, ge=8, le=72)
    color: str = Field("#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline_color: str = Field("#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline: float = Field(1.5, ge=0, le=6)
    bold: bool = False
    box: bool = False
    margin: int = Field(20, ge=0, le=200)

    def to_ass(self) -> str:
        """Render as the ``force_style`` string understood by libass."""

        border_style = 3 if self.box else 1
        back = "&H80000000" if self.box else "&H00000000"
        return ",".join(
            [
                f"FontName={self.font}",
                f"FontSize={self.size}",
                f"PrimaryColour={_ass_colour(self.color)}",
                f"OutlineColour={_ass_colour(self.outline_color)}",
                f"BackColour={back}",
                f"Bold={-1 if self.bold else 0}",
                f"BorderStyle={border_style}",
                f"Outline={self.outline:g}",
                "Shadow=0",
                f"MarginV={self.margin}",
            ]
        )


def _ass_colour(hex_rgb: str) -> str:
    red, green, blue = hex_rgb[1:3], hex_rgb[3:5], hex_rgb[5:7]
    return f"&H00{blue}{green}{red}".upper()


class JobOptions(BaseModel):
    """User overrides; ``None`` always means "use the preset default"."""

    model_config = ConfigDict(extra="forbid")

    preset_id: str = "mp4-h264"
    quality: int | None = Field(None, ge=0, le=100_000)
    speed: Speed = "balanced"
    accel: Accel = "auto"
    # Short-side limit in pixels: None keeps the preset default, 0 keeps the source size
    max_height: int | None = Field(None, ge=0, le=4320)
    audio_bitrate_kbps: int | None = Field(None, ge=8, le=1536)
    volume_db: float = Field(0.0, ge=-30, le=30)
    normalize_audio: bool = False
    # Position among the source audio tracks; None picks the default one (all tracks for remux)
    audio_track: int | None = Field(None, ge=0)
    subtitle_mode: SubtitleMode = "none"
    # Position among embedded subtitle tracks; None means the external file below
    subtitle_track: int | None = Field(None, ge=0)
    subtitle_file: str | None = None
    subtitle_style: SubtitleStyle = SubtitleStyle()
    output_dir: str | None = None
    output_name: str | None = Field(None, max_length=200)
