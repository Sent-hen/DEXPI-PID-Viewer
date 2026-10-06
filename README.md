# DEXPI P&ID Viewer

A lightweight, dependency-free, single-page viewer and validator for **DEXPI 2.0.1** XML P&ID files.

- **Specification:** [DEXPI Specification 2.0.1](https://dexpi.org/specification/2.0.1/html/)
  - [DEXPI XML exchange format](https://dexpi.org/specification/2.0.1/html/basics/metamodel_and_exchange_format.html)
  - [Core model](https://dexpi.org/specification/2.0.1/html/models/Core/model-index.html) · [Plant model](https://dexpi.org/specification/2.0.1/html/models/Plant/model-index.html) · [Reference P&ID](https://dexpi.org/specification/2.0.1/html/appendix/reference_pid.html)

## Usage

Open `index.html` in a browser, then click **Open…** or drag a `.xml` file onto the canvas. Nothing is uploaded; parsing happens locally.

To use the **Sample** button or the `?file=` URL parameter, serve the folder (browsers block `fetch` from `file://`):

```bash
python -m http.server 8765
```

Then open `http://localhost:8765/?file=samples/3bb1a46a89c0.dexpi.xml`.

### Features

- **Topology view**: DEXPI conceptual data doesn't need drawing coordinates, so the viewer builds a layered (Sugiyama-style) layout from the model:
  - Pipes, using `SourceItem`/`SourceNode` → `TargetItem`/`TargetNode`
  - Segments that have no `Connections`, drawn as implied lines
  - Instrument sensing locations, measuring lines and signal lines
- **Symbols** for equipment (tank, vessel, column, pump, heat exchanger), valves (operated, check, ball, globe, butterfly, safety), tees, reducers, flanges, off-page connectors, instrumentation functions and sensors. Any other component gets a generic symbol.
- **Inspector**: click a symbol to see its type, path, data, references, back-references and connections. Click a pipe to highlight its whole `PipingNetworkSystem`.
- **Validation panel**:
  - XML well-formedness, exchange-format structure, ID syntax and uniqueness, and IDREF resolution
  - With `metamodel.js` loaded: class existence and abstractness, declared properties, composition/reference/data kind, child and reference target types, and multiplicity bounds, all against the Core and Plant 2.0.1 metamodels
- **Model tree**, search by ID or tag (press Enter), toggles for instruments, unconnected items and labels, SVG export, and light/dark themes.

### Files

| Path | Purpose |
|---|---|
| `index.html` | The viewer (HTML/CSS/JS, no dependencies) |
| `metamodel.js` | Compact class table generated from DEXPI 2.0.1 `Core.xml` + `Plant.xml` (optional; enables metamodel checks) |
| `tools/validate.py` | CLI validator: XSD + metamodel checks (`pip install lxml`) |
| `tools/build_metamodel.py` | Regenerates `metamodel.js` from `tools/spec/` |
| `tools/spec/` | Official DEXPI 2.0.1 `DEXPI_XML_Schema.xsd`, `Core.xml`, `Plant.xml` |
| `samples/` | `3bb1a46a89c0.dexpi.xml` (pid-digitizer export) and the official DEXPI reference P&ID |

```bash
python tools/validate.py samples/3bb1a46a89c0.dexpi.xml
```

## Validation report: `samples/3bb1a46a89c0.dexpi.xml`

Both validators agree. The official reference P&ID passes with **0 errors**, which confirms the checks aren't over-reporting.

**XSD (DEXPI_XML_Schema.xsd): valid.** All 786 objects use existing concrete Plant/Core classes. Property names and kinds, child types, reference target types and upper bounds are all correct. Every IDREF resolves, and every ID is unique.

**Metamodel errors (3):** the `Core/EngineeringModel` header is missing three properties that are required (lower bound 1):

- `ExportDateTime`
- `OriginatingSystemVendorName`
- `OriginatingSystemVersion`

Only `OriginatingSystemName` is present. The fix is to add these elements to the `EngineeringModel` object:

```xml
<Data property="ExportDateTime"><DateTime>2026-10-06T00:00:00Z</DateTime></Data>
<Data property="OriginatingSystemVendorName"><String>…</String></Data>
<Data property="OriginatingSystemVersion"><String>…</String></Data>
```

**Content warnings.** These aren't violations, but they limit what any viewer can show:

- No `Diagram` component, so there is no drawing geometry and the viewer auto-lays-out the topology.
- 17 tanks have no `TagName`, and 65 `ProcessInstrumentationFunction`s have no category, letters or number. The viewer labels them by ID.
- 31 `PipingNetworkSegment`s (`SegItem_*`) contain only a valve, with no `Connections`, `SourceItem` or `TargetItem`. These valves float unconnected.
- 29 `PipingNode`s are never referenced by a pipe.
- Some pipes have only a source or only a target. The viewer draws these with a "line end" marker.

## Limitations

- `Core/Diagram` geometry (shapes, polylines, positions) isn't rendered. Files that include it are still shown as a topology view.
- Layout is automatic: it shows how items connect, not where they sit on the original drawing.

## License notice

The files in `tools/spec/` and `samples/reference_pid.dexpi.xml` come from the DEXPI Specification 2.0.1, © DEXPI, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). `metamodel.js` is derived from them.
