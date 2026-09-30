// careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla. Proprietary and confidential.
// Converts a real IFC file into the compact format web/bim.html loads:
//   <out>.bin   Float32 [x y z nx ny nz]* (all elements), then Uint32 indices
//   <out>.json  element table: IFC type, name, material, storey, property sets, buffer ranges
// Everything in the JSON comes from the IFC file itself; nothing is invented.
//   npm i web-ifc@0.0.66 && node scripts/ifc_to_web.mjs in.ifc web/models/structure
import * as WebIFC from "web-ifc";
import fs from "fs";
const [,, src, out] = process.argv;
const api = new WebIFC.IfcAPI();
api.SetWasmPath("./node_modules/web-ifc/", true);
await api.Init();
const id = api.OpenModel(new Uint8Array(fs.readFileSync(src)));
const val = v => (v && typeof v === "object" && "value" in v) ? v.value : v;

// storey per element, from the spatial tree
const storeyOf = new Map();
const tree = await api.properties.getSpatialStructure(id);
(function walk(n, storey) {
  const t = api.GetLineType(id, n.expressID);
  if (t === WebIFC.IFCBUILDINGSTOREY) storey = val(api.GetLine(id, n.expressID).Name);
  storeyOf.set(n.expressID, storey);
  (n.children || []).forEach(c => walk(c, storey));
})(tree, null);

const verts = [], idxs = [], elements = [];
let vBase = 0;
api.StreamAllMeshes(id, mesh => {
  const eid = mesh.expressID, line = api.GetLine(id, eid);
  const typeName = api.GetNameFromTypeCode(api.GetLineType(id, eid));
  const vOff = vBase, iOff = idxs.length;
  let color = null;
  const g = mesh.geometries;
  for (let i = 0; i < g.size(); i++) {
    const pg = g.get(i), geo = api.GetGeometry(id, pg.geometryExpressID);
    const v = api.GetVertexArray(geo.GetVertexData(), geo.GetVertexDataSize());
    const ix = api.GetIndexArray(geo.GetIndexData(), geo.GetIndexDataSize());
    const m = pg.flatTransformation;
    if (!color) color = [pg.color.x, pg.color.y, pg.color.z];
    for (let k = 0; k < v.length; k += 6) {
      const x = v[k], y = v[k+1], z = v[k+2], nx = v[k+3], ny = v[k+4], nz = v[k+5];
      verts.push(m[0]*x+m[4]*y+m[8]*z+m[12], m[1]*x+m[5]*y+m[9]*z+m[13], m[2]*x+m[6]*y+m[10]*z+m[14],
                 m[0]*nx+m[4]*ny+m[8]*nz, m[1]*nx+m[5]*ny+m[9]*nz, m[2]*nx+m[6]*ny+m[10]*nz);
    }
    const base = vBase;
    for (let k = 0; k < ix.length; k++) idxs.push(ix[k] + base);
    vBase += v.length / 6;
    geo.delete();
  }
  elements.push({ id: eid, type: typeName.replace(/^IFC/, ""), name: val(line.Name) || null, tag: val(line.Tag) || null,
    storey: storeyOf.get(eid) || null, color, vOff, vCount: vBase - vOff, iOff, iCount: idxs.length - iOff });
});

// property sets + material, straight from the file
for (const e of elements) {
  e.psets = {};
  try {
    for (const ps of await api.properties.getPropertySets(id, e.id, true)) {
      const nm = val(ps.Name); if (!nm || !ps.HasProperties) continue;
      const o = {};
      for (const p of ps.HasProperties) { const k = val(p.Name), v = val(p.NominalValue); if (k != null && v != null && v !== "") o[k] = v; }
      if (Object.keys(o).length) e.psets[nm] = o;
    }
  } catch {}
  try {
    const mats = await api.properties.getMaterialsProperties(id, e.id, true);
    const names = mats.map(m => val(m.Name) || val(m.ForLayerSet?.LayerSetName)).filter(Boolean);
    e.material = names[0] || null;
  } catch { e.material = null; }
}
const f32 = new Float32Array(verts), u32 = new Uint32Array(idxs);
fs.writeFileSync(out + ".bin", Buffer.concat([Buffer.from(f32.buffer), Buffer.from(u32.buffer)]));
const meta = { source: "ThatOpen/engine_web-ifc examples/example.ifc (IFC2X3, MPL-2.0)", vertexFloats: f32.length, indexCount: u32.length, elements };
fs.writeFileSync(out + ".json", JSON.stringify(meta));
console.log(elements.length, "elements,", f32.length / 6, "vertices,", u32.length / 3, "triangles");
const c = {}; elements.forEach(e => c[e.type] = (c[e.type] || 0) + 1); console.log(c);
console.log("storeys:", [...new Set(elements.map(e => e.storey))]);
console.log("with materials:", elements.filter(e => e.material).length, "with psets:", elements.filter(e => Object.keys(e.psets).length).length);
