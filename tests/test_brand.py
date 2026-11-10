"""Tests for Play24 brand assets and validation configuration."""

import struct
from pathlib import Path


def _get_png_dimensions(file_path: Path) -> tuple[int, int]:
    """Read width and height directly from PNG IHDR chunk."""
    data = file_path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{file_path} is not a valid PNG file"
    assert data[12:16] == b"IHDR", f"{file_path} missing IHDR chunk"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_brand_assets_exist_and_valid():
    """Verify that local brand assets comply with Home Assistant and HACS requirements."""
    brand_dir = Path(__file__).parent.parent / "custom_components" / "play24" / "brand"
    assert brand_dir.is_dir(), "brand directory must exist"

    icon = brand_dir / "icon.png"
    assert icon.is_file(), "brand/icon.png must exist"
    w, h = _get_png_dimensions(icon)
    assert (w, h) == (256, 256), f"icon.png must be 256x256, got {w}x{h}"

    icon_2x = brand_dir / "icon@2x.png"
    assert icon_2x.is_file(), "brand/icon@2x.png must exist"
    w, h = _get_png_dimensions(icon_2x)
    assert (w, h) == (512, 512), f"icon@2x.png must be 512x512, got {w}x{h}"

    logo = brand_dir / "logo.png"
    assert logo.is_file(), "brand/logo.png must exist"
    w, h = _get_png_dimensions(logo)
    assert 128 <= min(w, h) <= 256, f"logo.png shortest side must be 128-256px, got {w}x{h}"

    logo_2x = brand_dir / "logo@2x.png"
    assert logo_2x.is_file(), "brand/logo@2x.png must exist"
    w, h = _get_png_dimensions(logo_2x)
    assert 256 <= min(w, h) <= 512, f"logo@2x.png shortest side must be 256-512px, got {w}x{h}"


def test_root_assets_exist_and_valid():
    """Verify that root icon.png and logo.png are valid PNGs."""
    root_dir = Path(__file__).parent.parent
    for fname in ["icon.png", "logo.png"]:
        fpath = root_dir / fname
        assert fpath.is_file(), f"{fname} must exist in repo root"
        w, h = _get_png_dimensions(fpath)
        assert w > 0 and h > 0


def test_hacs_validation_does_not_ignore_brands():
    """Verify that CI workflow does not ignore brands check in HACS action."""
    wf_path = Path(__file__).parent.parent / ".github" / "workflows" / "validate.yaml"
    assert wf_path.is_file()
    content = wf_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        if "ignore:" in line:
            ignored = line.split(":", 1)[1].strip().strip('"').strip("'").split()
            assert "brands" not in ignored, f"'brands' should not be ignored in HACS action: {line}"
