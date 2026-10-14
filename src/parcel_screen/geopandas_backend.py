from math import isfinite
from pathlib import Path

import geopandas as gpd


POPUP_FIELDS = ("PRMSWARD", "PREMISEADD", "NBHDNAME", "NEWTOTAL")
PARCEL_FIELDS = ("OBJECTID", "PROPTYPE", "STATEDAREA", *POPUP_FIELDS)


def load_lots(
    path: Path,
    fields: tuple[str, ...] = PARCEL_FIELDS,
) -> gpd.GeoDataFrame:
    return gpd.read_parquet(path, columns=[*fields, "geometry"])


def feature_count(lots: gpd.GeoDataFrame) -> int:
    return len(lots)


def filter_options(
    lots: gpd.GeoDataFrame,
) -> tuple[list[str], list[str], list[str], float, float]:
    property_types = sorted(lots["PROPTYPE"].dropna().astype(str).unique().tolist())
    wards = sorted(lots["PRMSWARD"].dropna().astype(str).unique().tolist())
    neighborhoods = sorted(lots["NBHDNAME"].dropna().astype(str).unique().tolist())
    stated_areas = lots["STATEDAREA"].dropna()
    proposed_totals = lots["NEWTOTAL"].dropna()
    max_area = float(stated_areas.max()) if not stated_areas.empty else 0.0
    max_total = float(proposed_totals.max()) if not proposed_totals.empty else 0.0
    return property_types, wards, neighborhoods, max_area, max_total


def filter_lots(
    lots: gpd.GeoDataFrame,
    *,
    property_type: str | None = None,
    ward: str | None = None,
    neighborhood: str | None = None,
    min_area: float | None = None,
    max_area: float | None = None,
    min_total: float | None = None,
    max_total: float | None = None,
) -> gpd.GeoDataFrame:
    if min_area is not None and max_area is not None and min_area > max_area:
        raise ValueError("Minimum area must not exceed maximum area.")
    if min_total is not None and max_total is not None and min_total > max_total:
        raise ValueError("Minimum proposed total must not exceed maximum proposed total.")

    mask = None
    if property_type is not None:
        mask = lots["PROPTYPE"].eq(property_type)
    if ward is not None:
        ward_mask = lots["PRMSWARD"].astype(str).eq(ward)
        mask = ward_mask if mask is None else mask & ward_mask
    if neighborhood is not None:
        neighborhood_mask = lots["NBHDNAME"].astype(str).eq(neighborhood)
        mask = neighborhood_mask if mask is None else mask & neighborhood_mask
    if min_area is not None:
        area_mask = lots["STATEDAREA"].ge(min_area)
        mask = area_mask if mask is None else mask & area_mask
    if max_area is not None:
        area_mask = lots["STATEDAREA"].le(max_area)
        mask = area_mask if mask is None else mask & area_mask
    if min_total is not None:
        total_mask = lots["NEWTOTAL"].ge(min_total)
        mask = total_mask if mask is None else mask & total_mask
    if max_total is not None:
        total_mask = lots["NEWTOTAL"].le(max_total)
        mask = total_mask if mask is None else mask & total_mask
    return lots.loc[mask] if mask is not None else lots


def filter_lots_near(
    lots: gpd.GeoDataFrame,
    destinations: gpd.GeoDataFrame,
    *,
    max_distance_miles: float,
) -> gpd.GeoDataFrame:
    if not isfinite(max_distance_miles) or max_distance_miles < 0:
        raise ValueError("Maximum distance must be a finite, non-negative number.")
    if lots.crs is None or destinations.crs is None or not destinations.crs.is_projected:
        raise ValueError(
            "Parcel layers need a CRS and transit layers must use a projected CRS."
        )
    if lots.empty or destinations.empty:
        return lots.iloc[0:0]

    distance_units = (
        max_distance_miles
        * 1609.344
        / destinations.crs.axis_info[0].unit_conversion_factor
    )
    projected_lots = lots.to_crs(destinations.crs)
    valid_lots = projected_lots.loc[
        projected_lots.geometry.notna() & ~projected_lots.geometry.is_empty
    ]
    valid_destinations = destinations.loc[
        destinations.geometry.notna() & ~destinations.geometry.is_empty,
        [destinations.geometry.name],
    ]
    if valid_lots.empty or valid_destinations.empty:
        return lots.iloc[0:0]

    nearest = gpd.sjoin_nearest(
        valid_lots,
        valid_destinations,
        how="inner",
        max_distance=distance_units if distance_units > 0 else None,
        distance_col="_distance_units",
    )
    matched_indices = nearest.index[
        nearest["_distance_units"].le(distance_units)
    ].unique()
    return lots.loc[lots.index.isin(matched_indices)]
