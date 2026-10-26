#!/usr/bin/env python
"""Place-level politics and governance covariates for the ban/pause models.

The handoff place frame (alpr_handoff/external/data/model_frame_place.parquet)
carries demographics, roads, land use and cameras, but not the place-level
Trump share, incorporation, or police variables the draft's place models use.
This script builds them, keyed on the 7-character place GEOID:

  trump_2020           Trump share of all presidential votes, 2020. Block-group
                       votes from the VEST/RLCR reallocation (contiguous US),
                       summed over block groups whose interior point falls in the
                       place. Places containing no block-group interior point
                       (small places) take the share of the block group that
                       contains the place's own interior point.
  trump_2020_method    "bg_sum" | "bg_containing" | NA
  trump_2020_aip       1 - AIP demshare_pres (2020), for places AIP covers (check)
  aip_ideology         AIP MRP ideology, 2017-2021 survey period
  incorporated         1 unless the Census LSAD is 57 (census designated place)
  own_pd               1 if the city government reports police spending (CoG 2022 E62 > 0)
  log_own_police_pc    log(1 + own police spending per capita, $), 0 where no own PD

Run from the repo root:
  ~/flock_research/.venv/bin/python scripts/03_place_politics_governance.py

Inputs (cached; see alpr_pipeline/DATA_MANIFEST.md, data/raw/tiger):
  alpr_pipeline/data/cache/vest_realloc_contig_us.zip
  alpr_pipeline/data/cache/cb_2023_us_place_500k.zip
  alpr_pipeline/data/cache/aip_place_ideology.tab
  data/raw/tiger/cb_2020_us_bg_500k.zip   (www2.census.gov/geo/tiger/GENZ2020/shp/)
  data/out/place_police_2022.csv          (scripts/01_cog2022_police.R)
Output:
  data/out/place_politics_governance.csv
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

CACHE = Path.home() / "flock_research/alpr_pipeline/data/cache"
BG_ZIP = Path("data/raw/tiger/cb_2020_us_bg_500k.zip")
BG_URL = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_bg_500k.zip"
OUT = Path("data/out/place_politics_governance.csv")
CRS = "EPSG:5070"  # CONUS Albers, equal area

if not BG_ZIP.exists():
    raise SystemExit(f"missing {BG_ZIP}; curl -o {BG_ZIP} {BG_URL}")

# ---- block-group 2020 presidential votes -------------------------------------
with zipfile.ZipFile(CACHE / "vest_realloc_contig_us.zip") as z:
    raw = z.read("Contiguous USA - Main Method/Block Groups/bg-2020-RLCR.csv")
votes = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig", dtype={"bg_GEOID": str}, low_memory=False)
pres = [c for c in votes.columns if c.startswith("G20PRE")]
votes = pd.DataFrame({
    "bg_geoid": votes["bg_GEOID"].str.zfill(12),
    "trump": votes["G20PRERTRU"].fillna(0),
    "total": votes[pres].fillna(0).sum(axis=1),
})
print(f"block groups with votes: {len(votes):,}  (total votes {votes.total.sum():,.0f})")

# ---- geometries ----------------------------------------------------------------
bg = gpd.read_file(f"zip://{BG_ZIP}")[["GEOID", "geometry"]].rename(columns={"GEOID": "bg_geoid"}).to_crs(CRS)
pl = gpd.read_file(f"zip://{CACHE / 'cb_2023_us_place_500k.zip'}")[["GEOID", "LSAD", "geometry"]]
pl = pl.rename(columns={"GEOID": "place_geoid"}).to_crs(CRS)

# 1. block groups whose interior point lies inside a place
bg_pt = bg.assign(geometry=bg.representative_point())
hit = gpd.sjoin(bg_pt, pl[["place_geoid", "geometry"]], how="inner", predicate="within")
agg = (hit[["bg_geoid", "place_geoid"]].merge(votes, on="bg_geoid")
       .groupby("place_geoid")[["trump", "total"]].sum())
agg = agg[agg.total > 0]
share_sum = (agg.trump / agg.total).rename("trump_2020")

# 2. remaining places: the block group containing the place's interior point
pl_pt = pl.assign(geometry=pl.representative_point())
cont = gpd.sjoin(pl_pt[["place_geoid", "geometry"]], bg, how="inner", predicate="within")
cont = cont[["place_geoid", "bg_geoid"]].merge(votes, on="bg_geoid")
cont = cont[cont.total > 0].drop_duplicates("place_geoid").set_index("place_geoid")
share_cont = (cont.trump / cont.total).rename("trump_2020")

trump = pd.DataFrame({"trump_2020": share_sum, "trump_2020_method": "bg_sum"})
rest = share_cont[~share_cont.index.isin(trump.index)]
trump = pd.concat([trump, pd.DataFrame({"trump_2020": rest, "trump_2020_method": "bg_containing"})])

# ---- AIP (check measure + ideology) --------------------------------------------
aip = pd.read_csv(CACHE / "aip_place_ideology.tab", sep="\t", dtype={"place_fips": str})
aip = aip[aip.presidential_year == 2020].assign(place_geoid=lambda d: d.place_fips.str.zfill(7))
aip = aip.drop_duplicates("place_geoid").set_index("place_geoid")
aip = pd.DataFrame({"trump_2020_aip": 1 - aip.demshare_pres, "aip_ideology": aip.mrp_ideology})

# ---- governance ----------------------------------------------------------------
gov = pl[["place_geoid", "LSAD"]].assign(incorporated=lambda d: (d.LSAD != "57").astype(int)).set_index("place_geoid")
police = pd.read_csv("data/out/place_police_2022.csv", dtype={"place_geoid": str})
police = police.groupby("place_geoid").agg(e62=("police_current_E62_k", "sum"), pop=("pop_cog", "sum"))
police["own_pd"] = (police.e62 > 0).astype(int)
police["log_own_police_pc"] = np.log1p(np.where(police["pop"] > 0, 1000 * police.e62 / police["pop"], 0))

out = (gov[["incorporated"]].join(trump, how="left").join(aip, how="left")
       .join(police[["own_pd", "log_own_police_pc"]], how="left"))
out["own_pd"] = out.own_pd.fillna(0).astype(int)
out["log_own_police_pc"] = out.log_own_police_pc.fillna(0.0)
out.index.name = "place_geoid"
OUT.parent.mkdir(parents=True, exist_ok=True)
out.reset_index().to_csv(OUT, index=False)

# ---- report --------------------------------------------------------------------
print(f"places: {len(out):,}  -> {OUT}")
print(out.trump_2020_method.value_counts(dropna=False).to_string())
both = out.dropna(subset=["trump_2020", "trump_2020_aip"])
print(f"corr(trump_2020, AIP 1-demshare) = {both.trump_2020.corr(both.trump_2020_aip):.3f} on {len(both):,} places")
print(f"incorporated share {out.incorporated.mean():.3f}; own_pd share {out.own_pd.mean():.3f}")
