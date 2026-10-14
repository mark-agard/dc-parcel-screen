import argparse
from pathlib import Path

import geopandas as gpd

from parcel_screen.geopandas_backend import PARCEL_FIELDS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "Common_Ownership_Lots.geojson"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "Common_Ownership_Lots.parquet"
TRANSPORT_LAYER_FILES = (
    "Capital_Bike_Share_Locations.geojson",
    "Metro_Bus_Stops.geojson",
    "Metro_Stations_(Regional).geojson",
)
SIMPLIFICATION_TOLERANCE_METERS = 1.0


def prepare_lots(input_path: Path, output_path: Path) -> tuple[int, str]:
    if not input_path.is_file():
        raise FileNotFoundError(f"Source parcel file not found: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("The output path must not overwrite the source file.")

    lots = gpd.read_file(
        input_path,
        engine="pyogrio",
        use_arrow=True,
        columns=list(PARCEL_FIELDS),
    )
    if lots.crs is None:
        raise ValueError("The source parcel file has no coordinate reference system.")

    source_crs = lots.crs
    projected_crs = lots.estimate_utm_crs()
    if projected_crs is None:
        raise ValueError("Could not estimate a projected CRS for parcel simplification.")

    lots = lots.to_crs(projected_crs)
    lots.geometry = lots.geometry.simplify(
        tolerance=SIMPLIFICATION_TOLERANCE_METERS,
        preserve_topology=True,
    )
    lots = lots.to_crs(source_crs)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lots.to_parquet(output_path, index=False, compression="zstd")
    return len(lots), projected_crs.to_string()


def prepare_transport_layer(
    input_path: Path,
    output_path: Path,
    projected_crs: str,
) -> int:
    if not input_path.is_file():
        raise FileNotFoundError(f"Transport layer not found: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("The output path must not overwrite the source file.")

    layer = gpd.read_file(input_path, engine="pyogrio", use_arrow=True)
    if layer.crs is None:
        raise ValueError(f"The transport layer has no coordinate reference system: {input_path}")

    layer = layer.to_crs(projected_crs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    layer.to_parquet(output_path, index=False, compression="zstd")
    return len(layer)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare parcel and transport layers as GeoParquet files."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    parcel_count, projected_crs = prepare_lots(args.input, args.output)
    print(f"Wrote {parcel_count:,} parcels to {args.output}")
    print(f"Using projected CRS {projected_crs} for transport layers")

    for filename in TRANSPORT_LAYER_FILES:
        input_path = PROJECT_ROOT / "data" / filename
        output_path = input_path.with_suffix(".parquet")
        count = prepare_transport_layer(input_path, output_path, projected_crs)
        print(f"Wrote {count:,} features to {output_path}")


if __name__ == "__main__":
    main()
