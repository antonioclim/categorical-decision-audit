# Native editable figures for Paper M R07

The three `.odg` files are the editable masters. They contain individual native
LibreOffice Draw text boxes, rectangles and lines. No raster image, embedded SVG
or foreign chart object stands in for the editable figure. Text remains text,
including numbers, axis labels and the quantisation symbol λ.

| Figure | Native objects | Editable text boxes | Master size |
|---|---:|---:|---|
| 1 Shared completion | 35 | 24 | 178 × 107 mm |
| 2 Discounted sensitivity | 90 | 42 | 178 × 125 mm |
| 3 Scale sensitivity | 82 | 39 | 178 × 132 mm |

Each matching PDF is a vector export from LibreOffice Draw with embedded fonts.
The matching PNG is a 600 dpi rendering for document embedding and preview.
The minimum native type size is 9.5 pt; at 163 mm document width this becomes
approximately 8.7 pt. The PDFs contain no embedded raster image.

## Edit in LibreOffice Draw

Open an `.odg` master in LibreOffice Draw. Click an object to select it; double
click a text box to edit its characters. The Position and Size dialogue changes
an object's dimensions and position. Each bar, grid line, matrix cell, tick,
legend key and label is separate. Tab cycles through objects. Object names are
recorded in `source_data/native_objects.json` so a particular plotted element
can be identified without guessing its purpose.

Edit a copy when experimenting. Changing a bar or a number without updating its
data creates an inconsistent figure; the regeneration route below keeps the
objects consistent with the recorded source values.

## Regenerate and export

Run from this directory with Python 3.12 or a compatible Python 3 installation:

```bash
python scripts/build_figures.py
python scripts/export_figures.py
```

The builder uses only the Python standard library and the aggregate data in
`source_data/figure_data.json`. It creates deterministic ODG files with fixed ZIP
timestamps. No passage identifiers, relevance labels, source run files or witness
assignments are required. Figure 1 contains only a public query identifier and
aggregate counts. The CSV files expose the plotted numbers for inspection.

Export requires LibreOffice (`soffice` or `libreoffice`) and Poppler's
`pdftoppm` on PATH. The export script creates a separate temporary LibreOffice
profile, exports vector PDFs and renders the PNGs at 600 dpi. PDF timestamps and
font subsets can differ between LibreOffice versions; the editable source
geometry and source values remain fixed. No network access is used.

## Checks performed

`qa/editability_audit.json` records the native object audit and the edit test.
Copies were edited through native ODF XML: a context label, an axis label, a data
rectangle's width and, where present, an axis line endpoint were changed. Each
copy was then opened and saved as ODG by LibreOffice, reopened and exported to
PDF. The changed values and native object counts survived. The clean research
masters remained unchanged. This is a native file-format and application
roundtrip test; it is not a claim that interactive GUI operations were exercised.

`qa/vector_metadata_audit.json` records one-page vector PDF checks, embedded
fonts, anonymous metadata and file hashes. All three clean rendered figures
were visually inspected after correcting the initial text-box padding. The
development build used LibreOfficeDev 26.8.0.0.alpha0. Regeneration with another
version should be inspected for layout drift before submission.

To repeat the editability test on temporary copies:

```bash
python scripts/audit_editability.py
```

The script leaves edited test copies below `qa/editability/`. Those copies are
test evidence and must never be used as manuscript figures. The clean masters
are the three ODG files in this directory.

## Data and captions

`source_data/figure_data.json` identifies the phase-2 result files by SHA-256.
Counts come from the validated complete enumeration. The joint matrix uses common completions and equal attainable support;
it does not assert equality of marginal count distributions. The bar properties
in Figure 2 overlap. Figure 3 deliberately separates cases from completions.

`Figure_Captions_EN.md` and `captions.json` provide captions for integration.
The plots were constructed deterministically from recorded data. Publication
and submission are outside this private phase.

The brief figure titles appear only in the external captions, as requested by
the journal. Cohort labels, axis labels and panel headings remain in the graphics.

The caption and metadata update is recorded in `qa/editorial_update.json`.
It leaves the source data, native drawing content and PDF/PNG exports unchanged.
Earlier checks are identified by their retained hashes and scopes.
