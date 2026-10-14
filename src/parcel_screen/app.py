from pathlib import Path

import geopandas as gpd
import pydeck as pdk
import streamlit as st

from parcel_screen import geopandas_backend


project_root = Path(__file__).resolve().parents[2]
data_path = project_root / "data" / "Common_Ownership_Lots.parquet"
transport_data_paths = {
    "bike_share": project_root / "data" / "Capital_Bike_Share_Locations.parquet",
    "bus_stops": project_root / "data" / "Metro_Bus_Stops.parquet",
    "metro_stations": project_root / "data" / "Metro_Stations_(Regional).parquet",
}
map_widget_key = "parcel-map"

st.set_page_config(page_title="DC Parcel Screen", layout="wide")
st.title("DC Parcel Screen")


@st.cache_resource(show_spinner="Loading prepared parcel data...")
def load_parcel_data(
    path: Path,
    fields: tuple[str, ...],
) -> tuple[gpd.GeoDataFrame, list[str], list[str], list[str], float, float]:
    lots = geopandas_backend.load_lots(path, fields)
    property_types, wards, neighborhoods, max_area, max_total = (
        geopandas_backend.filter_options(lots)
    )
    return lots, property_types, wards, neighborhoods, max_area, max_total


@st.cache_resource(show_spinner="Loading prepared transit layers...")
def load_transport_layers(
    paths: tuple[tuple[str, Path], ...],
) -> dict[str, gpd.GeoDataFrame]:
    return {name: gpd.read_parquet(path) for name, path in paths}


missing_data_paths = [
    path for path in (data_path, *transport_data_paths.values()) if not path.is_file()
]
if missing_data_paths:
    missing_names = ", ".join(path.name for path in missing_data_paths)
    st.error(
        f"Prepared data is missing: {missing_names}. "
        "Create it with `uv run python -m parcel_screen.prepare_data`."
    )
    st.stop()

try:
    loaded_data, property_types, wards, neighborhoods, max_area, max_total = (
        load_parcel_data(data_path, geopandas_backend.PARCEL_FIELDS)
    )
    transport_layers = load_transport_layers(tuple(transport_data_paths.items()))
except Exception as error:
    st.error(f"Could not load the parcel and transit datasets: {error}")
    st.stop()

with st.sidebar:
    with st.form("parcel_filter_form", enter_to_submit=False):
        st.header("Select filters")
        with st.expander("Parcel attributes", expanded=True):
            selected_property_type = st.selectbox(
                "Property Type",
                ["All property types", *property_types],
                key="property-type",
            )
            selected_ward = st.selectbox(
                "Ward",
                ["All wards", *wards],
                key="ward-filter",
            )
            selected_neighborhood = st.selectbox(
                "Neighborhood",
                ["All neighborhoods", *neighborhoods],
                key="neighborhood-filter",
            )
            minimum_area, maximum_area = st.columns(2)
            min_area = minimum_area.number_input(
                "Min Stated Area (sq ft)",
                min_value=0.0,
                max_value=max_area,
                value=0.0,
                step=1.0,
                format="%.0f",
                key="min-area",
            )
            selected_max_area = maximum_area.number_input(
                "Max Stated Area (sq ft)",
                min_value=0.0,
                max_value=max_area,
                value=max_area,
                step=1.0,
                format="%.0f",
                key="max-area",
            )
            minimum_total, maximum_total = st.columns(2)
            min_total = minimum_total.number_input(
                "Min Proposed Total",
                min_value=0.0,
                max_value=max_total,
                value=0.0,
                step=1000.0,
                format="%.0f",
                key="min-proposed-total",
            )
            selected_max_total = maximum_total.number_input(
                "Max Proposed Total",
                min_value=0.0,
                max_value=max_total,
                value=max_total,
                step=1000.0,
                format="%.0f",
                key="max-proposed-total",
            )

        with st.expander("Transit accessibility", expanded=False):
            bike_share_distance = st.number_input(
                "Within ___ miles of Capital Bikeshare",
                min_value=0.0,
                max_value=50.0,
                value=0.0,
                step=0.1,
                format="%.1f",
                key="bike-share-distance",
            )
            bus_stop_distance = st.number_input(
                "Within ___ miles of a Metro bus stop",
                min_value=0.0,
                max_value=50.0,
                value=0.0,
                step=0.1,
                format="%.1f",
                key="bus-stops-distance",
            )
            metro_station_distance = st.number_input(
                "Within ___ miles of a Metro station",
                min_value=0.0,
                max_value=50.0,
                value=0.0,
                step=0.1,
                format="%.1f",
                key="metro-stations-distance",
            )

        apply_filters = st.form_submit_button("Apply filters", type="primary")

    if apply_filters:
        for key in ("parcel_filter_summary", "parcel_map_geojson", "parcel_results"):
            st.session_state.pop(key, None)
        st.session_state.pop(map_widget_key, None)

        if min_area > selected_max_area:
            st.warning("Minimum Stated Area (sq ft) must not exceed the maximum.")
        elif min_total > selected_max_total:
            st.warning("Minimum Proposed Total must not exceed the maximum.")
        else:
            try:
                filtered_lots = geopandas_backend.filter_lots(
                    loaded_data,
                    property_type=(
                        None
                        if selected_property_type == "All property types"
                        else selected_property_type
                    ),
                    ward=None if selected_ward == "All wards" else selected_ward,
                    neighborhood=(
                        None
                        if selected_neighborhood == "All neighborhoods"
                        else selected_neighborhood
                    ),
                    min_area=None if min_area == 0 else min_area,
                    max_area=None if selected_max_area == max_area else selected_max_area,
                    min_total=None if min_total == 0 else min_total,
                    max_total=(
                        None if selected_max_total == max_total else selected_max_total
                    ),
                )
                for layer_key, max_distance in (
                    ("bike_share", bike_share_distance),
                    ("bus_stops", bus_stop_distance),
                    ("metro_stations", metro_station_distance),
                ):
                    if max_distance > 0:
                        filtered_lots = geopandas_backend.filter_lots_near(
                            filtered_lots,
                            transport_layers[layer_key],
                            max_distance_miles=max_distance,
                        )
                map_fields = [
                    "OBJECTID",
                    *geopandas_backend.POPUP_FIELDS,
                    "STATEDAREA",
                    "geometry",
                ]
                map_lots = filtered_lots.loc[
                    filtered_lots.geometry.notna(), map_fields
                ].copy()
                st.session_state["parcel_map_geojson"] = map_lots.__geo_interface__
                st.session_state["parcel_results"] = filtered_lots
                st.session_state["parcel_filter_summary"] = {
                    "matching_count": len(filtered_lots),
                }
            except Exception as error:
                st.error(f"Could not apply filters: {error}")

    filter_summary = st.session_state.get("parcel_filter_summary")
    parcel_results = st.session_state.get("parcel_results")
    if filter_summary:
        st.write(f"{filter_summary['matching_count']:,} matching lots")
    if parcel_results is not None:
        with st.expander("Download results", expanded=False):
            geojson_data = parcel_results.to_json(drop_id=True)
            csv_data = parcel_results.drop(columns="geometry").to_csv(index=False)
            st.download_button(
                "Download GeoJSON",
                data=geojson_data,
                file_name="dc-parcel-screen-results.geojson",
                mime="application/geo+json",
                on_click="ignore",
                width="stretch",
            )
            st.download_button(
                "Download CSV",
                data=csv_data,
                file_name="dc-parcel-screen-results.csv",
                mime="text/csv",
                on_click="ignore",
                width="stretch",
            )

map_layers = []
map_data = st.session_state.get("parcel_map_geojson")
map_widget_state = st.session_state.get(map_widget_key)
selected_indices = []
if map_widget_state is not None:
    selected_indices = map_widget_state.selection.indices.get("parcel-layer", [])

if map_data:
    map_layers.append(
        pdk.Layer(
            "GeoJsonLayer",
            id="parcel-layer",
            data=map_data,
            stroked=True,
            filled=True,
            get_fill_color=[235, 145, 40, 65],
            get_line_color=[160, 85, 10, 180],
            line_width_min_pixels=0.5,
            pickable=True,
            auto_highlight=True,
        )
    )
    map_features = map_data.get("features", [])
    selected_map_features = [
        map_features[index]
        for index in selected_indices
        if 0 <= index < len(map_features)
    ]
    if selected_map_features:
        map_layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                id="selected-parcel-layer",
                data={"type": "FeatureCollection", "features": selected_map_features},
                stroked=True,
                filled=True,
                get_fill_color=[255, 190, 40, 150],
                get_line_color=[30, 70, 150, 255],
                line_width_min_pixels=3,
                pickable=False,
            )
        )

map_deck = pdk.Deck(
    initial_view_state=pdk.ViewState(
        latitude=38.9072,
        longitude=-77.0369,
        zoom=11,
        pitch=0,
        bearing=0,
    ),
    map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    layers=map_layers,
)
st.markdown(
    """
    <style>
    .st-key-map_shell {
        position: relative;
    }
    .st-key-parcel_details {
        position: absolute;
        top: 1rem;
        right: 4rem;
        z-index: 10;
        width: min(22rem, calc(100% - 6rem));
        max-height: calc(100% - 2rem);
        overflow-y: auto;
        background-color: #ffffff !important;
        color: #1f2933 !important;
        border: 1px solid #d1d5db;
        border-radius: 0.75rem;
        padding: 1rem;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.18);
    }
    .st-key-parcel_details [data-testid="stMarkdownContainer"],
    .st-key-parcel_details [data-testid="stMarkdownContainer"] *,
    .st-key-parcel_details h1,
    .st-key-parcel_details h2,
    .st-key-parcel_details h3 {
        color: #1f2933 !important;
    }
    .st-key-parcel_details button {
        color: #1f2933 !important;
        background-color: #f3f4f6 !important;
        border-color: #d1d5db !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.container(key="map_shell"):
    map_state = st.pydeck_chart(
        map_deck,
        width="stretch",
        height=720,
        on_select="rerun",
        selection_mode="single-object",
        key=map_widget_key,
    )
    selected_features = map_state.selection.objects.get("parcel-layer", [])
    selected_feature = selected_features[0] if selected_features else None
    properties = (
        selected_feature.get("properties", selected_feature)
        if selected_feature is not None
        else {}
    )
    if selected_feature is not None:
        with st.container(key="parcel_details", border=True):
            st.subheader("Selected parcel")
            for label, field in (
                ("Premise Ward", "PRMSWARD"),
                ("Premise Address", "PREMISEADD"),
                ("Neighborhood Assessment Name", "NBHDNAME"),
                ("Stated Area (sq ft)", "STATEDAREA"),
                ("Proposed Total Value", "NEWTOTAL"),
            ):
                value = properties.get(field)
                if field == "PRMSWARD" and value is not None:
                    value = f"Ward {value}"
                elif field in ("STATEDAREA", "NEWTOTAL") and value is not None:
                    try:
                        numeric_value = float(value)
                        if field == "STATEDAREA" and numeric_value < 0:
                            value = "Not available"
                        elif field == "NEWTOTAL":
                            value = f"${numeric_value:,.0f}"
                        else:
                            value = f"{numeric_value:,.0f}"
                    except (TypeError, ValueError):
                        pass
                display_value = value if value is not None else "Not available"
                if field in ("PREMISEADD", "NBHDNAME"):
                    st.markdown(f"**{label}:**  \n{display_value}")
                else:
                    st.write(f"**{label}:** {display_value}")
