# Data processing notes

Every dataset that ends up in a data package, a study area or a paper has a **processing note** here. The note says where the data came from, what was done to it (in QGIS or elsewhere), and how to check the result. It is the source for the "Data" sections of the papers and for the provenance listed in each data package manifest.

## Layout

```
docs/data-processing/
├── README.md                 this file
├── TEMPLATE.md               copy this for a new note
└── DP-001-osm-road-network.md, DP-002-elstat-population.md, ...

data-processing/              (repo root) reproducible processing files
├── qgis/
│   ├── models/               QGIS Processing models (.model3)
│   ├── scripts/              PyQGIS / Processing scripts (.py)
│   └── projects/             QGIS project files (.qgz), relative paths only
└── styles/                   layer styles (.qml) used in QGIS and for checking

data/local/                   real input and output data (git-ignored, never committed)
```

## Rules

1. **One note per processed dataset**, named `DP-NNN-short-name.md`, numbered in order. Never renumber.
2. **Record every step**, including manual edits. For QGIS tools, copy the exact call from **Processing → History** (it shows the algorithm id and all parameters as Python) into the note.
3. **Make it repeatable.** If a sequence of steps will be run again (for example for another municipality or a data update), turn it into a **Processing model** (`.model3`, built with the Graphical Modeler) or a script in `data-processing/qgis/`, and link it from the note. Manual edits that cannot be automated (for example fixing a misplaced facility) are listed one by one with the reason.
4. **QGIS projects use relative paths** (Project → Properties → General → Save paths: Relative) and point to `data/local/`. No absolute paths such as `C:\Users\...`.
5. **No real data in git.** Inputs and outputs live in `data/local/`. Only notes, models, scripts, styles and projects are committed. Operational or personal data are never processed here.
6. **Record versions:** QGIS version (Help → About), plugin versions, and the date and version of each source dataset.
7. **Checks are part of the note:** what was compared, counts before and after, CRS, a screenshot of the result if useful (store it next to the note, small PNG).
8. **Licences:** each source is also listed in `docs/data-sources.md`. If processing creates a derived database (for example from OpenStreetMap, ODbL), note the attribution and share-alike obligations.
9. **Link to packages:** the `manifest.json` of each data package lists the `DP-NNN` notes of the data it contains.
10. If a processing step changes something the method depends on (for example how population is assigned to units), add an entry to `docs/specs/paper-revisions.md` or an open question.
