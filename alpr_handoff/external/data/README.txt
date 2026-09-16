Analysis-ready datasets. All Parquet; read GEOID columns as CHARACTER.

  model_frame_tract.parquet    84,415 tracts   (primary analysis frame)
  model_frame_place.parquet    32,041 places
  model_frame_county.parquet    3,235 counties
  model_frame_zcta.parquet     33,791 ZCTAs
  camera_dataset.parquet      124,416 cameras x 284 cols
  cameras_geocoded.parquet    camera points with geography keys

Each model_frame covers the COMPLETE universe of units, including those with
zero cameras. Do not filter to camera-bearing units before modelling -- that
conditions on the outcome and overstates the mean count by 2.2x.

Not included (rebuildable, and large): the HTTP response cache (2.4 GB), TIGER
shapefiles (1.4 GB), fitted .rds model objects (262 MB), and CSV duplicates of
the parquet files.
