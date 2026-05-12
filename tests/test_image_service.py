from pathlib import Path

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qiao_wechat.db import Base
from qiao_wechat.services.image_service import ImageService


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_materialize_asset_reuses_existing_row(tmp_path: Path):
    image_path = tmp_path / "cover.png"
    Image.new("RGB", (16, 12), "white").save(image_path)
    db = _session()

    service = ImageService(db)
    first, first_blob = service.materialize_asset(account_id=1, source=str(image_path), purpose="cover")
    second, second_blob = service.materialize_asset(account_id=1, source=str(image_path), purpose="cover")

    assert first.id == second.id
    assert first_blob.sha256 == second_blob.sha256
    assert first.width == 16
    assert first.height == 12


def test_prepare_asset_for_wechat_converts_svg_to_png(tmp_path: Path):
    svg_path = tmp_path / "diagram.svg"
    svg_path.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80" viewBox="0 0 120 80">
        <rect width="120" height="80" fill="#ffffff"/>
        <circle cx="40" cy="40" r="24" fill="#4a90e2"/>
        <rect x="68" y="20" width="28" height="40" fill="#43aa8b"/>
        </svg>""",
        encoding="utf-8",
    )
    db = _session()

    service = ImageService(db)
    asset, blob = service.prepare_asset_for_wechat(account_id=1, source=str(svg_path), purpose="inline")

    assert asset.id is not None
    assert blob.path.suffix.lower() == ".png"
    assert blob.mime_type == "image/png"
    assert blob.width == 120
    assert blob.height == 80
    assert blob.path.exists()
