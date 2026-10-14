import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import streamlit as st
from shapely.geometry import Point, box
from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "src" / "parcel_screen" / "app.py"
PREPARED_FILES = {
    "Common_Ownership_Lots.parquet",
    "Capital_Bike_Share_Locations.parquet",
    "Metro_Bus_Stops.parquet",
    "Metro_Stations_(Regional).parquet",
}


class ParcelScreenFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        parcels = gpd.GeoDataFrame(
            {
                "OBJECTID": [101, 102, 103, 104],
                "PROPTYPE": ["HOTEL", "HOTEL", "CONDO", "HOTEL"],
                "STATEDAREA": [5000.0, 5000.0, 5000.0, 12000.0],
                "PRMSWARD": ["5", "5", "5", "2"],
                "PREMISEADD": ["1 A St", "2 A St", "3 A St", "4 B St"],
                "NBHDNAME": [
                    "Capitol Hill",
                    "Capitol Hill",
                    "Capitol Hill",
                    "Anacostia",
                ],
                "NEWTOTAL": [750000.0, 750000.0, 750000.0, 950000.0],
            },
            geometry=[
                box(500100, 4300100, 500130, 4300130),
                box(501000, 4300000, 501030, 4300030),
                box(500100, 4300100, 500130, 4300130),
                box(500100, 4300100, 500130, 4300130),
            ],
            crs="EPSG:32618",
        )
        cls.fixtures = {
            "Common_Ownership_Lots.parquet": parcels.to_crs("EPSG:4326"),
            "Capital_Bike_Share_Locations.parquet": gpd.GeoDataFrame(
                geometry=[Point(520000, 4300000)],
                crs="EPSG:32618",
            ),
            "Metro_Bus_Stops.parquet": gpd.GeoDataFrame(
                geometry=[Point(500000, 4300000)],
                crs="EPSG:32618",
            ),
            "Metro_Stations_(Regional).parquet": gpd.GeoDataFrame(
                geometry=[Point(520000, 4400000)],
                crs="EPSG:32618",
            ),
        }

    def setUp(self) -> None:
        st.cache_resource.clear()
        self.read_parquet_patcher = patch.object(
            gpd,
            "read_parquet",
            side_effect=self._read_parquet,
        )
        original_is_file = Path.is_file

        def is_file(path: Path) -> bool:
            if path.name in PREPARED_FILES:
                return True
            return original_is_file(path)

        self.is_file_patcher = patch.object(Path, "is_file", new=is_file)
        self.read_parquet_patcher.start()
        self.is_file_patcher.start()
        self.addCleanup(self.read_parquet_patcher.stop)
        self.addCleanup(self.is_file_patcher.stop)

    def _read_parquet(
        self,
        path: str | Path,
        columns: list[str] | None = None,
    ) -> gpd.GeoDataFrame:
        frame = self.fixtures[Path(path).name]
        return frame.loc[:, columns].copy() if columns is not None else frame.copy()

    def _run_app(self) -> AppTest:
        return AppTest.from_file(str(APP_PATH)).run(timeout=30)

    def test_zero_distance_defaults_leave_transit_filters_off(self) -> None:
        app = self._run_app()

        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(
            [item.value for item in app.number_input[4:7]],
            [0.0, 0.0, 0.0],
        )

        app.button[0].click().run(timeout=30)

        object_ids = {
            feature["properties"]["OBJECTID"]
            for feature in app.session_state["parcel_map_geojson"]["features"]
        }
        self.assertEqual(object_ids, {101, 102, 103, 104})

    def test_attribute_and_bus_distance_filters_select_expected_parcel(self) -> None:
        app = self._run_app()
        app.selectbox[0].select("HOTEL")
        app.selectbox[1].select("5")
        app.selectbox[2].select("Capitol Hill")
        app.number_input[2].set_value(700000.0)
        app.number_input[3].set_value(800000.0)
        app.number_input[5].set_value(0.1)
        app.button[0].click().run(timeout=30)

        object_ids = {
            feature["properties"]["OBJECTID"]
            for feature in app.session_state["parcel_map_geojson"]["features"]
        }
        self.assertEqual(object_ids, {101})
        self.assertFalse(app.exception)
        self.assertFalse(app.error)


if __name__ == "__main__":
    unittest.main()
