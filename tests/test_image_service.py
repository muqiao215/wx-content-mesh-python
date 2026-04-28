from pathlib import Path

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from wx_content_mesh.db import Base
from wx_content_mesh.services.image_service import ImageService


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
