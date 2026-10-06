"""Validate a DEXPI 2.0.1 XML file: XSD + semantic checks against Core/Plant metamodels."""
import sys, os, collections
from lxml import etree

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec")
MODELS = {"Core": "Core.xml", "Plant": "Plant.xml"}

# ---- load metamodel -------------------------------------------------------
classes = {}  # "Plant/Piping.Pipe" -> dict(abstract, supers[], props{name: (kind, type, lower, upper)})

def qualify(ref, cur):
    pre, _, path = ref.partition("/")
    return f"{pre or cur}/{path}"

def walk(el, model, path):
    for c in el:
        if not isinstance(c.tag, str):
            continue
        if c.tag == "Package":
            walk(c, model, path + [c.get("name")])
        elif c.tag in ("ConcreteClass", "AbstractClass"):
            fq = f"{model}/{'.'.join(path + [c.get('name')])}"
            props = {}
            for p in c:
                if p.tag in ("CompositionProperty", "ReferenceProperty", "DataProperty"):
                    tref = p.find("ClassReference")
                    if tref is None:
                        tref = p.find("DataTypeReference")
                    t = qualify(tref.get("type"), model) if tref is not None else None
                    up = p.get("upper")
                    props[p.get("name")] = (p.tag, t, int(p.get("lower", "0")), int(up) if up else None)
            classes[fq] = dict(abstract=c.tag == "AbstractClass",
                               supers=[qualify(s, model) for s in (c.get("superTypes") or "").split()],
                               props=props)

for prefix, fn in MODELS.items():
    walk(etree.parse(os.path.join(HERE, fn)).getroot(), prefix, [])

def ancestors(t):
    seen, stack = [], [t]
    while stack:
        x = stack.pop()
        if x in seen or x not in classes:
            continue
        seen.append(x)
        stack.extend(classes[x]["supers"])
    return seen

def find_prop(t, name):
    for a in ancestors(t):
        if name in classes[a]["props"]:
            return classes[a]["props"][name]
    return None

# ---- validate instance ----------------------------------------------------
def main(path):
    errors, warnings = [], []
    doc = etree.parse(path)
    schema = etree.XMLSchema(etree.parse(os.path.join(HERE, "DEXPI_XML_Schema.xsd")))
    if schema.validate(doc):
        print("XSD: valid")
    else:
        for e in schema.error_log:
            errors.append(f"XSD line {e.line}: {e.message}")

    root = doc.getroot()
    imports = {i.get("prefix"): i.get("source") for i in root.findall("Import")}
    for p in ("Core", "Plant"):
        if p in imports and "2.0.1" not in imports[p]:
            warnings.append(f"Import {p} points to {imports[p]} (not 2.0.1)")

    objs = root.iter("Object")
    ids = collections.Counter(o.get("id") for o in root.iter("Object") if o.get("id"))
    for i, n in ids.items():
        if n > 1:
            errors.append(f"Duplicate id {i} ({n}x)")
    byid = {o.get("id"): o for o in root.iter("Object") if o.get("id")}

    # incoming refs for multiplicity of opposite ends not checked (lenient)
    for o in root.iter("Object"):
        t, oid = o.get("type"), o.get("id") or "(anon)"
        if t not in classes:
            errors.append(f"{oid}: unknown type {t}")
            continue
        if classes[t]["abstract"]:
            errors.append(f"{oid}: type {t} is abstract")
        counts = collections.Counter()
        for c in o:
            if not isinstance(c.tag, str):
                continue
            pname = c.get("property")
            prop = find_prop(t, pname)
            if prop is None:
                errors.append(f"{oid} ({t}): property '{pname}' not declared")
                continue
            kind, ptype, lo, up = prop
            expect = {"Components": "CompositionProperty", "References": "ReferenceProperty", "Data": "DataProperty"}[c.tag]
            if kind != expect:
                errors.append(f"{oid}: '{pname}' is a {kind} but used as <{c.tag}>")
                continue
            if c.tag == "Components":
                vals = [x for x in c if isinstance(x.tag, str)]
                for v in vals:
                    vt = v.get("type")
                    if v.tag == "Object" and vt in classes and ptype not in ancestors(vt):
                        errors.append(f"{oid}.{pname}: child {v.get('id')} type {vt} not a {ptype}")
                counts[pname] += len(vals)
            elif c.tag == "References":
                refs = c.get("objects", "").split()
                for r in refs:
                    if r.startswith("#"):
                        tgt = byid.get(r[1:])
                        if tgt is None:
                            errors.append(f"{oid}.{pname}: dangling ref {r}")
                        elif ptype not in ancestors(tgt.get("type")):
                            errors.append(f"{oid}.{pname}: {r} is {tgt.get('type')}, expected {ptype}")
                counts[pname] += len(refs)
            else:
                counts[pname] += len([x for x in c if isinstance(x.tag, str)])
        for pname, n in counts.items():
            _, _, lo, up = find_prop(t, pname)
            if up is not None and n > up:
                errors.append(f"{oid}: '{pname}' has {n} values, upper bound {up}")
        # lower bounds
        for a in ancestors(t):
            for pname, (kind, _, lo, _) in classes[a]["props"].items():
                if lo > 0 and counts[pname] < lo:
                    errors.append(f"{oid} ({t}): required '{pname}' missing (lower={lo})")

    # ---- topology / content quality checks (not schema violations) -------
    types = collections.Counter(o.get("type") for o in root.iter("Object"))
    referenced = set()
    for r in root.iter("References"):
        referenced.update(x[1:] for x in r.get("objects", "").split() if x.startswith("#"))
    for o in root.iter("Object"):
        t = o.get("type")
        if t == "Plant/Piping.PipingNode" and o.get("id") not in referenced:
            warnings.append(f"PipingNode {o.get('id')} is never connected")
    no_data = sum(1 for o in root.iter("Object") if o.find("Data") is None)
    tagged = [o for o in root.iter("Object") if o.get("type", "").startswith("Plant/ProcessEquipment.")
              and find_prop(o.get("type"), "TagName") and o.find("Data[@property='TagName']") is None]
    if tagged:
        warnings.append(f"{len(tagged)} equipment items have no TagName")
    pif_nolabel = [o for o in root.iter("Object") if o.get("type") == "Plant/Instrumentation.ProcessInstrumentationFunction" and o.find("Data") is None]
    if pif_nolabel:
        warnings.append(f"{len(pif_nolabel)} instrumentation functions have no Data (no category/number/letters)")
    eng = root.find("Object[@type='Core/EngineeringModel']")
    if eng is not None and eng.find("Components[@property='Diagram']") is None:
        warnings.append("No Diagram component: file has no graphical layout (viewer must auto-layout)")

    segs = [o for o in root.iter("Object") if o.get("type") == "Plant/Piping.PipingNetworkSegment"]
    n = sum(1 for s in segs if s.find("Components[@property='Connections']") is None)
    if n:
        warnings.append(f"{n} piping segments have no Connections (items are not connected to anything)")
    print("Types:", dict(types))
    print(f"Errors: {len(errors)}")
    for e in errors[:60]:
        print("  E", e)
    agg = collections.Counter(w.split(" ")[0] if w.startswith("PipingNode") else w for w in warnings)
    print(f"Warnings: {len(warnings)}")
    for w, n in agg.items():
        print(f"  W {w}" + (f"  x{n}" if n > 1 else ""))
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
