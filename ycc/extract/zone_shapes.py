"""Extraction and reprojection of TLC taxi zone shapefiles."""

import hashlib
import io
import json
import logging
import os
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import duckdb
import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform as transform_geometry
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ycc.config import Settings
from ycc.load.s3 import ObjectStorage

logger = logging.getLogger(__name__)

TLC_ZONE_SHAPES_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip"
_CHUNK_SIZE = 64 * 1024


def _is_retryable(error: BaseException) -> bool:
    if isinstance(error, HTTPError):
        return 500 <= error.code < 600
    return isinstance(error, (OSError, TimeoutError, URLError))


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def _download_zone_archive(destination: Path) -> None:
    """Stream and atomically save the public TLC zone-shape archive."""
    request = Request(
        TLC_ZONE_SHAPES_URL,
        headers={"User-Agent": "YellowCabConfessions/0.1"},
    )
    partial_path = destination.with_suffix(".zip.part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(request, timeout=60) as response, partial_path.open("wb") as target:
            if response.status < 200 or response.status >= 300:
                raise OSError(f"Unexpected HTTP status {response.status} for {TLC_ZONE_SHAPES_URL}")
            while chunk := response.read(_CHUNK_SIZE):
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        os.replace(partial_path, destination)
    finally:
        partial_path.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _shape_archive(archive_path: Path, geojson_path: Path, centroids_path: Path) -> int:
    """Reproject archive features to WGS84 and write GeoJSON and centroid parquet."""
    with zipfile.ZipFile(archive_path) as archive:
        shp_name = next(
            (name for name in archive.namelist() if name.lower().endswith(".shp")), None
        )
        prj_name = next(
            (name for name in archive.namelist() if name.lower().endswith(".prj")), None
        )
        dbf_name = next(
            (name for name in archive.namelist() if name.lower().endswith(".dbf")), None
        )
        shx_name = next(
            (name for name in archive.namelist() if name.lower().endswith(".shx")), None
        )
        if not shp_name or not prj_name or not dbf_name or not shx_name:
            raise ValueError("TLC zone archive is missing a required shapefile component.")
        source_crs = CRS.from_wkt(archive.read(prj_name).decode("utf-8"))
        transformer = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True)
        reader = shapefile.Reader(
            shp=io.BytesIO(archive.read(shp_name)),
            shx=io.BytesIO(archive.read(shx_name)),
            dbf=io.BytesIO(archive.read(dbf_name)),
        )
        field_names = [field[0].casefold() for field in reader.fields[1:]]
        features: list[dict[str, object]] = []
        centroid_rows: list[dict[str, object]] = []
        for geometry, record in zip(reader.shapes(), reader.records(), strict=True):
            attributes = dict(zip(field_names, record, strict=True))
            zone_id = int(attributes["locationid"])
            wgs84 = transform_geometry(transformer.transform, shape(geometry.__geo_interface__))
            simplified = wgs84.simplify(0.0001, preserve_topology=True)
            centroid = wgs84.centroid
            centroid_rows.append(
                {
                    "zone_id": zone_id,
                    "centroid_lat": centroid.y,
                    "centroid_lon": centroid.x,
                }
            )
            features.append(
                {
                    "type": "Feature",
                    "geometry": simplified.__geo_interface__,
                    "properties": {
                        "LocationID": zone_id,
                        "borough": attributes.get("borough"),
                        "zone": attributes.get("zone"),
                        "service_zone": attributes.get("service_zone"),
                    },
                }
            )

    if not features:
        raise ValueError("TLC zone archive contains no geometries.")
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    geojson_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
        encoding="utf-8",
    )
    connection = duckdb.connect()
    try:
        connection.execute(
            """
            CREATE TABLE zone_centroids (
                zone_id INTEGER,
                centroid_lat DOUBLE,
                centroid_lon DOUBLE
            )
            """
        )
        connection.executemany(
            "INSERT INTO zone_centroids VALUES (?, ?, ?)",
            [(row["zone_id"], row["centroid_lat"], row["centroid_lon"]) for row in centroid_rows],
        )
        connection.execute(
            "COPY zone_centroids TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(centroids_path)],
        )
    finally:
        connection.close()
    return len(features)


def extract_zone_shapes(
    settings: Settings,
    storage: ObjectStorage,
) -> tuple[Path, Path]:
    """Download the TLC zone archive, then export simplified WGS84 files."""
    archive_path = settings.download_dir / "taxi_zones.zip"
    geojson_path = settings.work_dir / "zones.geojson"
    centroids_path = settings.work_dir / "zone_centroids.parquet"
    if not all(path.is_file() for path in (archive_path, geojson_path, centroids_path)):
        _download_zone_archive(archive_path)
        feature_count = _shape_archive(archive_path, geojson_path, centroids_path)
    else:
        connection = duckdb.connect()
        try:
            feature_count = int(
                connection.execute(
                    "SELECT count(*) FROM read_parquet(?)",
                    [str(centroids_path)],
                ).fetchone()[0]
            )
        finally:
            connection.close()

    for path, key, content_type in (
        (
            archive_path,
            "raw/zones/taxi_zones.zip",
            "application/zip",
        ),
        (
            centroids_path,
            "raw/zones/zone_centroids.parquet",
            "application/vnd.apache.parquet",
        ),
    ):
        checksum = _sha256_file(path)
        if not storage.object_matches(key, checksum):
            storage.upload_file(
                path,
                key,
                sha256=checksum,
                source_etag=None,
                content_type=content_type,
            )

    logger.info(
        "zones.shapes.extract.completed",
        extra={
            "feature_count": feature_count,
            "geojson_bytes": geojson_path.stat().st_size,
            "centroid_bytes": centroids_path.stat().st_size,
        },
    )
    return geojson_path, centroids_path
