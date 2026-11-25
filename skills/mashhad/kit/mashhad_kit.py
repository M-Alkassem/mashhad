"""Mashhad kit: building blocks for cinematic Blender scenes, written for Claude to direct.

Import it at the top of a scene script (scripts/mashhad.py adds this folder to sys.path):

    import mashhad_kit as mk
    mk.new_scene(seconds=5)
    ...
    mk.save()

Every function returns the Blender objects it makes, so a scene can keep adjusting them.
Units are metres, Z is up, the hero subject usually sits near the origin, the camera looks along +Y.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import urllib.request
from pathlib import Path

import bpy
from mathutils import Vector

# ----------------------------------------------------------------------------------------------
# scene
# ----------------------------------------------------------------------------------------------

STATE = {"out": None, "fps": 24, "frames": 120}


def _args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def new_scene(seconds: float = 5.0, fps: int = 24, look: str = "AgX - Punchy") -> bpy.types.Scene:
    """Empty scene with filmic colour (AgX). The .blend path comes from the command line."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.render.fps = fps
    sc.frame_start, sc.frame_end = 1, max(2, round(seconds * fps))
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = look
    except TypeError:
        pass
    sc.render.image_settings.file_format = "PNG"
    STATE.update(fps=fps, frames=sc.frame_end)
    args = _args()
    STATE["out"] = args[0] if args else None
    return sc


def save(path: str | None = None) -> str:
    path = path or STATE["out"] or os.path.join(os.getcwd(), "scene.blend")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(path))
    print("MASHHAD_SAVED", path)
    return path


def frames() -> int:
    return bpy.context.scene.frame_end


def look_at(obj, target) -> None:
    """Point a camera or light (their -Z axis) at a point or object."""
    t = target.location if hasattr(target, "location") else Vector(target)
    obj.rotation_euler = (Vector(t) - obj.location).to_track_quat("-Z", "Y").to_euler()


def collection(name: str) -> bpy.types.Collection:
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(c)
    return c


def bounds(obj) -> tuple[Vector, Vector]:
    """World-space min and max corners (evaluated, so modifiers count)."""
    bpy.context.view_layer.update()
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return (
        Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
        Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))),
    )


def place_on_floor(obj, z: float = 0.0) -> None:
    lo, _ = bounds(obj)
    obj.location.z += z - lo.z


def fit(obj, size: float, axis: str = "max") -> None:
    """Uniformly scale so the object's largest (or x/y/z) dimension equals size metres."""
    bpy.context.view_layer.update()
    d = obj.dimensions
    cur = {"x": d.x, "y": d.y, "z": d.z}.get(axis, max(d))
    if cur > 1e-9:
        obj.scale = obj.scale * (size / cur)


# ----------------------------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------------------------


def _mat(name: str):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    return m, nt.nodes, nt.links, nt.nodes["Principled BSDF"]


def assign(obj, material) -> None:
    """Replace every material slot on obj (and its mesh children) with material."""
    for o in [obj, *obj.children_recursive]:
        if hasattr(o.data, "materials"):
            o.data.materials.clear()
            o.data.materials.append(material)


def _rough_variation(n, l, b, lo: float, hi: float, scale: float = 14.0) -> None:
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    mr = n.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = lo, hi
    l.new(noise.outputs["Fac"], mr.inputs["Value"])
    l.new(mr.outputs["Result"], b.inputs["Roughness"])


METALS = {
    "gold": (1.0, 0.71, 0.29),
    "rose_gold": (0.95, 0.64, 0.54),
    "silver": (0.97, 0.96, 0.92),
    "copper": (0.95, 0.64, 0.54),
    "brass": (0.91, 0.78, 0.42),
    "titanium": (0.62, 0.6, 0.58),
    "black_chrome": (0.06, 0.06, 0.07),
}


def metal(kind: str = "gold", roughness: float = 0.18, brushed: bool = False, name: str | None = None):
    """Metal. kind: gold, rose_gold, silver, copper, brass, titanium, black_chrome, or an (r,g,b).
    brushed=True: stretched, satin highlights (caps, watch cases, cards) instead of a mirror polish."""
    color = METALS.get(kind, kind) if isinstance(kind, str) else kind
    m, n, l, b = _mat(name or f"Metal_{kind}")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = 1.0
    if brushed:
        b.inputs["Roughness"].default_value = max(roughness, 0.25)
        b.inputs["Anisotropic"].default_value = 0.8
    else:
        # very slight, large-scale variation; fine noise reads as sandy grain at low samples
        _rough_variation(n, l, b, max(0.02, roughness - 0.025), roughness + 0.025, scale=3.0)
    return m


def glass(tint=(1, 1, 1), roughness: float = 0.0, ior: float = 1.45, name: str = "Glass"):
    m, n, l, b = _mat(name)
    b.inputs["Base Color"].default_value = (*tint, 1)
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Roughness"].default_value = roughness
    b.inputs["IOR"].default_value = ior
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"  # EEVEE: see through it
    if hasattr(m, "use_raytrace_refraction"):
        m.use_raytrace_refraction = True
    return m


def ceramic(color=(0.92, 0.9, 0.86), roughness: float = 0.25, name: str = "Ceramic"):
    """Glazed ceramic or porcelain: a coat layer over a soft diffuse body."""
    m, n, l, b = _mat(name)
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Coat Weight"].default_value = 1.0
    b.inputs["Coat Roughness"].default_value = 0.04
    b.inputs["Subsurface Weight"].default_value = 0.08
    return m


def plastic(color=(0.05, 0.05, 0.05), roughness: float = 0.35, name: str = "Plastic"):
    m, n, l, b = _mat(name)
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = roughness
    return m


def liquid(color=(0.06, 0.025, 0.01), roughness: float = 0.02, name: str = "Liquid"):
    """Dark glossy liquid surface (coffee, wine, oil). Pair with a ripple() for life."""
    m, n, l, b = _mat(name)
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Specular IOR Level"].default_value = 0.7
    return m


def emission(color=(1, 0.7, 0.35), strength: float = 5.0, name: str = "Glow"):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    n.remove(n["Principled BSDF"])
    e = n.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1)
    e.inputs["Strength"].default_value = strength
    l.new(e.outputs["Emission"], n["Material Output"].inputs["Surface"])
    return m


def dark_water(ripple_scale: float = 2.4, ripple: float = 0.18, name: str = "DarkWater"):
    """Black mirror water: reflections do the work. Stretched noise for wind ripples."""
    m, n, l, b = _mat(name)
    b.inputs["Base Color"].default_value = (0.004, 0.005, 0.007, 1)
    b.inputs["Roughness"].default_value = 0.05
    tc, mp, noise, bump = (n.new(t) for t in ("ShaderNodeTexCoord", "ShaderNodeMapping", "ShaderNodeTexNoise", "ShaderNodeBump"))
    mp.inputs["Scale"].default_value = (1.0, 2.2, 1.0)
    noise.inputs["Scale"].default_value = ripple_scale
    noise.inputs["Detail"].default_value = 6
    bump.inputs["Strength"].default_value = ripple
    bump.inputs["Distance"].default_value = 0.02
    l.new(tc.outputs["Object"], mp.inputs["Vector"])
    l.new(mp.outputs["Vector"], noise.inputs["Vector"])
    l.new(noise.outputs["Fac"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def pbr(asset_id: str, res: str = "2k", scale: float = 1.0, name: str | None = None):
    """A real scanned surface from Poly Haven (wood, stone, plaster, fabric…), CC0.
    Browse ids at https://polyhaven.com/textures. scale = how many metres one tile covers."""
    maps = polyhaven_texture(asset_id, res)
    m, n, l, b = _mat(name or asset_id)
    tc, mp = n.new("ShaderNodeTexCoord"), n.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / scale, 1 / scale, 1 / scale)
    l.new(tc.outputs["UV"], mp.inputs["Vector"])

    def img(path, non_color):
        t = n.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(path, check_existing=True)
        if non_color:
            t.image.colorspace_settings.name = "Non-Color"
        l.new(mp.outputs["Vector"], t.inputs["Vector"])
        return t

    if "diff" in maps:
        l.new(img(maps["diff"], False).outputs["Color"], b.inputs["Base Color"])
    if "rough" in maps:
        l.new(img(maps["rough"], True).outputs["Color"], b.inputs["Roughness"])
    if "nor_gl" in maps:
        nm = n.new("ShaderNodeNormalMap")
        l.new(img(maps["nor_gl"], True).outputs["Color"], nm.inputs["Color"])
        l.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


# ----------------------------------------------------------------------------------------------
# Poly Haven assets (free, CC0) with a local cache
# ----------------------------------------------------------------------------------------------

CACHE = Path(os.environ.get("MASHHAD_CACHE", Path.home() / ".cache" / "mashhad" / "polyhaven"))
_UA = {"User-Agent": "mashhad-blender-kit"}


def _get(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.rename(dest)
    print(f"MASHHAD_DOWNLOADED {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def _files(asset_id: str) -> dict:
    meta = CACHE / asset_id / "files.json"
    if not meta.exists():
        _get(f"https://api.polyhaven.com/files/{asset_id}", meta)
    return json.loads(meta.read_text())


def polyhaven_texture(asset_id: str, res: str = "2k") -> dict[str, str]:
    files, out = _files(asset_id), {}
    for key, short in (("Diffuse", "diff"), ("Rough", "rough"), ("nor_gl", "nor_gl")):
        if key in files and res in files[key]:
            f = files[key][res]["jpg"] if "jpg" in files[key][res] else next(iter(files[key][res].values()))
            out[short] = str(_get(f["url"], CACHE / asset_id / res / Path(f["url"]).name))
    return out


def polyhaven_hdri(asset_id: str, res: str = "2k") -> str:
    f = _files(asset_id)["hdri"][res]
    f = f.get("exr") or f["hdr"]
    return str(_get(f["url"], CACHE / asset_id / Path(f["url"]).name))


def polyhaven_model(asset_id: str, res: str = "1k", collection_name: str | None = None):
    """Import a Poly Haven model (glTF + textures). Returns one parent empty you can move and scale.
    Browse ids at https://polyhaven.com/models."""
    g = _files(asset_id)["gltf"][res]["gltf"]
    root = CACHE / asset_id / f"gltf_{res}"
    main = _get(g["url"], root / Path(g["url"]).name)
    for rel, inc in g.get("include", {}).items():
        _get(inc["url"], root / rel)
    return import_model(str(main), name=asset_id, collection_name=collection_name)


def import_model(path: str, name: str = "Model", collection_name: str | None = None):
    """Import .glb/.gltf/.obj/.fbx/.blend-free formats and wrap them under one empty, centred on its base."""
    before = set(bpy.data.objects)
    ext = Path(path).suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext in (".usd", ".usdz", ".usdc", ".usda"):
        bpy.ops.wm.usd_import(filepath=path)
    else:
        raise ValueError(f"unsupported model format: {ext}")
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new(name, None)
    (collection(collection_name) if collection_name else bpy.context.scene.collection).objects.link(root)
    for o in new:
        if o.parent is None:
            o.parent = root
    bpy.context.view_layer.update()
    meshes = [o for o in new if o.type == "MESH"]
    if meshes:
        pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        cx = (min(p.x for p in pts) + max(p.x for p in pts)) / 2
        cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2
        z0 = min(p.z for p in pts)
        for o in new:
            if o.parent is root:
                o.location -= Vector((cx, cy, z0))
        root["mashhad_size"] = max(
            max(p.x for p in pts) - min(p.x for p in pts),
            max(p.y for p in pts) - min(p.y for p in pts),
            max(p.z for p in pts) - z0,
        )
    return root


def scale_to(root, size: float) -> None:
    """Scale an imported model (from import_model/polyhaven_model) so its largest side is size metres."""
    cur = root.get("mashhad_size", 1.0)
    root.scale = (size / cur,) * 3


# ----------------------------------------------------------------------------------------------
# shapes Claude can build well from code
# ----------------------------------------------------------------------------------------------


def svg_logo(path: str, width: float = 2.4, depth: float = 0.07, bevel: float = 0.012, upright: bool = True, name: str = "Logo"):
    """A logo or wordmark from an SVG, extruded into a solid. width in metres. Stands on z=0 facing -Y."""
    before = set(bpy.data.objects)
    bpy.ops.import_curve.svg(filepath=path)
    curves = [o for o in bpy.data.objects if o not in before and o.type == "CURVE"]
    if not curves:
        raise ValueError(f"no shapes found in {path}")
    bpy.ops.object.select_all(action="DESELECT")
    for o in curves:
        o.select_set(True)
    bpy.context.view_layer.objects.active = curves[0]
    if len(curves) > 1:
        bpy.ops.object.join()
    logo = bpy.context.view_layer.objects.active
    logo.name = name
    for c in list(logo.users_collection):
        c.objects.unlink(logo)
    bpy.context.scene.collection.objects.link(logo)
    cu = logo.data
    cu.extrude = cu.bevel_depth = 0.0
    cu.dimensions = "3D"  # 2D curves refuse transform_apply
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    pts = [Vector(p.co) for sp in cu.splines for p in sp.bezier_points] + [p.co.to_3d() for sp in cu.splines for p in sp.points]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), 0))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), 0))
    centre, s = (lo + hi) / 2, width / max(hi.x - lo.x, 1e-9)
    for sp in cu.splines:
        for p in sp.bezier_points:
            for attr in ("co", "handle_left", "handle_right"):
                v = (getattr(p, attr) - centre) * s
                v.z = 0
                setattr(p, attr, v)
        for p in sp.points:
            v = (p.co.to_3d() - centre) * s
            p.co = (v.x, v.y, 0, p.co.w)
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.extrude = depth
    cu.bevel_depth = bevel
    cu.bevel_resolution = 4
    cu.resolution_u = 24
    cu.materials.clear()
    logo.location = (0, 0, 0)
    if upright:
        logo.rotation_euler = (math.radians(90), 0, 0)
        place_on_floor(logo)
    return logo


def text(body: str, size: float = 1.0, depth: float = 0.05, bevel: float | None = None, font: str | None = None, name: str = "Text"):
    """3D text for Latin, Greek, Cyrillic scripts. For Arabic/Hebrew/Indic text, shape it to an SVG
    first (SKILL.md, 'Text in any language') and use svg_logo().
    bevel defaults to 0.6% of size, and to none below 5 cm: tiny bevels on small type (a bottle label)
    make spiky geometry that shows as drips under letters."""
    if bevel is None:
        bevel = 0.0 if size < 0.05 else size * 0.006
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    if font:
        cu.font = bpy.data.fonts.load(font, check_existing=True)
    cu.size = size
    cu.extrude = depth
    cu.bevel_depth = bevel
    cu.bevel_resolution = 3
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_euler = (math.radians(90), 0, 0)
    place_on_floor(ob)
    return ob


def lathe(profile: list[tuple[float, float]], name: str = "Lathe", segments: int = 96, thickness: float = 0.0, smooth: int = 2):
    """Spin a side profile around Z: cups, bottles, vases, bowls, lamps, chess pieces.
    profile: [(radius, height), ...] from bottom to top, in metres. thickness > 0 gives a wall."""
    verts = [(r, 0.0, z) for r, z in profile]
    edges = [(i, i + 1) for i in range(len(verts) - 1)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, [])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    sc = ob.modifiers.new("Spin", "SCREW")
    sc.angle = math.tau
    sc.steps = sc.render_steps = segments
    sc.use_merge_vertices = True
    sc.use_normal_calculate = True
    if thickness > 0:
        so = ob.modifiers.new("Wall", "SOLIDIFY")
        so.thickness = thickness
        so.offset = -1
    if smooth:
        sd = ob.modifiers.new("Smooth", "SUBSURF")
        sd.levels = sd.render_levels = smooth
    for p in me.polygons:
        p.use_smooth = True
    return ob


def rounded_box(size=(1, 1, 1), radius: float = 0.05, name: str = "Box", segments: int = 6):
    """A box with softly rounded edges: devices, cards, plinths, buttons."""
    bpy.ops.mesh.primitive_cube_add(size=1)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bv = ob.modifiers.new("Round", "BEVEL")
    bv.width = radius
    bv.segments = segments
    bv.limit_method = "ANGLE"
    bpy.ops.object.shade_smooth()
    return ob


def rounded_panel(width: float = 1.712, height: float = 1.08, thickness: float = 0.02, radius: float = 0.07, edge: float = 0.004, name: str = "Panel", corner_steps: int = 12):
    """A thin slab with properly rounded corners: cards, phones, tablets, signs, tiles.
    Stands upright in the XZ plane facing -Y, centred on the origin. edge = soft edge bevel."""
    import bmesh

    bm = bmesh.new()
    hw, hh, r = width / 2, height / 2, min(radius, width / 2, height / 2)
    pts = []
    for cx, cz, a0 in ((hw - r, hh - r, 0), (-hw + r, hh - r, 90), (-hw + r, -hh + r, 180), (hw - r, -hh + r, 270)):
        for i in range(corner_steps + 1):
            a = math.radians(a0 + 90 * i / corner_steps)
            pts.append((cx + r * math.cos(a), -thickness / 2, cz + r * math.sin(a)))
    face = bm.faces.new([bm.verts.new(p) for p in pts])
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)], vec=(0, thickness, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if edge > 0:
        bv = ob.modifiers.new("Edge", "BEVEL")
        bv.width = edge
        bv.segments = 3
        bv.limit_method = "ANGLE"
        bv.angle_limit = math.radians(50)
        wn = ob.modifiers.new("Normals", "WEIGHTED_NORMAL")
        wn.keep_sharp = True
    for poly in me.polygons:
        poly.use_smooth = True
    return ob


def floor(material=None, size: float = 60.0, name: str = "Floor"):
    bpy.ops.mesh.primitive_plane_add(size=size)
    ob = bpy.context.active_object
    ob.name = name
    if material:
        ob.data.materials.append(material)
    return ob


def cyclorama(material=None, width: float = 30.0, depth: float = 20.0, height: float = 12.0, curve: float = 3.0, name: str = "Cyc"):
    """Photo-studio backdrop: floor that bends up into a back wall with no visible seam."""
    prof, steps = [], 16
    prof.append((-depth / 2, 0.0))
    y0 = depth / 2 - curve
    prof.append((y0, 0.0))
    for i in range(1, steps + 1):
        a = (math.pi / 2) * i / steps
        prof.append((y0 + curve * math.sin(a), curve - curve * math.cos(a)))
    prof.append((depth / 2, height))
    verts, faces = [], []
    for x in (-width / 2, width / 2):
        verts += [(x, y, z) for y, z in prof]
    n = len(prof)
    faces = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if material:
        me.materials.append(material)
    return ob


def scatter(obj, count: int, area=((-1, 1), (-1, 1)), z: float = 0.0, scale=(0.8, 1.2), seed: int = 1, rotate: bool = True):
    """Linked copies of obj spread over an XY area (beans, pebbles, petals, coins)."""
    rnd = random.Random(seed)
    out = []
    for _ in range(count):
        c = obj.copy()
        bpy.context.scene.collection.objects.link(c)
        c.location = (rnd.uniform(*area[0]), rnd.uniform(*area[1]), z)
        c.scale = obj.scale * rnd.uniform(*scale)
        if rotate:
            c.rotation_euler = (rnd.uniform(0, math.tau), rnd.uniform(0, math.tau), rnd.uniform(0, math.tau))
        out.append(c)
    return out


# ----------------------------------------------------------------------------------------------
# atmosphere
# ----------------------------------------------------------------------------------------------


def haze(density: float = 0.01, color=(1.0, 0.86, 0.68), anisotropy: float = 0.55, center=(0, 2, 7), size=(40, 40, 14), name: str = "Haze"):
    """A box of thin fog so light beams show. Keep density 0.005-0.02; more turns the frame grey."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    n.remove(n["Principled BSDF"])
    v = n.new("ShaderNodeVolumePrincipled")
    v.inputs["Density"].default_value = density
    v.inputs["Anisotropy"].default_value = anisotropy
    v.inputs["Color"].default_value = (*color, 1)
    l.new(v.outputs["Volume"], n["Material Output"].inputs["Volume"])
    ob.data.materials.append(m)
    return ob


def dust(count: int = 220, area=((-4, 4), (-6, 4), (0.2, 4.2)), color=(1.0, 0.68, 0.3), strength: float = 2.2, radius: float = 0.006, drift=(0.1, 0, 0.25), seed: int = 7, name: str = "Dust"):
    """Glowing specks floating in the light; with shallow focus they become bokeh. Drifts over the shot."""
    rnd = random.Random(seed)
    me = bpy.data.meshes.new(name + "Points")
    me.from_pydata([tuple(rnd.uniform(*a) for a in area) for _ in range(count)], [], [])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=radius, location=(0, 0, 0))
    sp = bpy.context.active_object
    sp.name = name + "Speck"
    sp.parent = ob
    sp.data.materials.append(emission(color, strength, name + "Glow"))
    ob.instance_type = "VERTS"
    ob.keyframe_insert("location", frame=1)
    ob.location = Vector(ob.location) + Vector(drift)
    ob.keyframe_insert("location", frame=frames())
    return ob


def steam(origin=(0, 0, 0.1), radius: float = 0.04, height: float = 0.35, density: float = 60.0, name: str = "Steam"):
    """Soft rising wisps (coffee, tea, soup, a hot drink). A volume shaped from noise that is sized
    to the steam itself, fades out to the sides and the top, and rises over the shot.
    Backlight it (the light behind, camera in front) against a dark background."""
    w_ = radius * 3.0
    bpy.ops.mesh.primitive_cylinder_add(radius=w_, depth=height, location=(origin[0], origin[1], origin[2] + height / 2))
    ob = bpy.context.active_object
    ob.name = name
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    n.remove(n["Principled BSDF"])

    def node(t, **inputs):
        x = n.new(t)
        for k, v in inputs.items():
            x.inputs[k].default_value = v
        return x

    tc = n.new("ShaderNodeTexCoord")
    # wisps: noise in steam-relative space, stretched upward, slowly evolving and rising
    mp = node("ShaderNodeMapping", Scale=(1 / radius, 1 / radius, 0.3 / radius))
    l.new(tc.outputs["Object"], mp.inputs["Vector"])
    noise = node("ShaderNodeTexNoise", Scale=0.9, Detail=6.0, Roughness=0.6, Distortion=1.2)
    noise.noise_dimensions = "4D"
    l.new(mp.outputs["Vector"], noise.inputs["Vector"])
    wisps = node("ShaderNodeMapRange", **{"From Min": 0.56, "From Max": 0.74})
    l.new(noise.outputs["Fac"], wisps.inputs["Value"])
    # fade toward the sides (widening as it rises) and toward the top
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(tc.outputs["Object"], sep.inputs["Vector"])
    flat = n.new("ShaderNodeCombineXYZ")
    l.new(sep.outputs["X"], flat.inputs["X"])
    l.new(sep.outputs["Y"], flat.inputs["Y"])
    rad = n.new("ShaderNodeVectorMath")
    rad.operation = "LENGTH"
    l.new(flat.outputs["Vector"], rad.inputs[0])
    up = node("ShaderNodeMapRange", **{"From Min": -height / 2, "From Max": height / 2, "To Min": 0.0, "To Max": 1.0})
    l.new(sep.outputs["Z"], up.inputs["Value"])
    spread = node("ShaderNodeMapRange", **{"From Min": 0.0, "From Max": 1.0, "To Min": radius, "To Max": w_})
    l.new(up.outputs["Result"], spread.inputs["Value"])
    side = n.new("ShaderNodeMath")
    side.operation = "DIVIDE"
    l.new(rad.outputs["Value"], side.inputs[0])
    l.new(spread.outputs["Result"], side.inputs[1])
    side_fade = node("ShaderNodeMapRange", **{"From Min": 1.0, "From Max": 0.2, "To Min": 0.0, "To Max": 1.0})
    l.new(side.outputs["Value"], side_fade.inputs["Value"])
    top_fade = node("ShaderNodeMapRange", **{"From Min": 1.0, "From Max": 0.15, "To Min": 0.0, "To Max": 1.0})
    l.new(up.outputs["Result"], top_fade.inputs["Value"])
    a = n.new("ShaderNodeMath")
    a.operation = "MULTIPLY"
    l.new(wisps.outputs["Result"], a.inputs[0])
    l.new(side_fade.outputs["Result"], a.inputs[1])
    b = n.new("ShaderNodeMath")
    b.operation = "MULTIPLY"
    l.new(a.outputs["Value"], b.inputs[0])
    l.new(top_fade.outputs["Result"], b.inputs[1])
    d = n.new("ShaderNodeMath")
    d.operation = "MULTIPLY"
    d.inputs[1].default_value = density
    l.new(b.outputs["Value"], d.inputs[0])
    v = node("ShaderNodeVolumePrincipled", Color=(1, 1, 1, 1), Anisotropy=0.45)
    l.new(d.outputs["Value"], v.inputs["Density"])
    l.new(v.outputs["Volume"], n["Material Output"].inputs["Volume"])
    ob.data.materials.append(m)
    ob["mashhad_steam"] = True
    # rise: noise drifts down in its own space (so wisps travel up) and slowly changes shape
    wv = noise.inputs["W"]
    wv.default_value = 0.0
    wv.keyframe_insert("default_value", frame=1)
    wv.default_value = 1.5
    wv.keyframe_insert("default_value", frame=frames())
    loc = mp.inputs["Location"]
    loc.default_value = (0, 0, 0)
    loc.keyframe_insert("default_value", frame=1)
    loc.default_value = (0, 0, -height * 2.2)
    loc.keyframe_insert("default_value", frame=frames())
    return ob


def gobo(kind: str = "mashrabiya", size: float = 6.0, location=(-2.6, 5.0, 5.2), face=None, name: str = "Gobo"):
    """Real geometry between a light and the scene to cut shaped shadows and light shafts.
    kind: mashrabiya (8-point lattice), blinds (venetian slats), window (four panes).
    Hidden from camera and reflections; only its shadow shows. face: point it at the light."""
    import bmesh

    bm = bmesh.new()
    half = size / 2

    def bar(cx, cy, w, h, rot=0.0):
        vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        for v in vs:
            v.co.x, v.co.y, v.co.z = v.co.x * w, v.co.y * h, v.co.z * 0.05
            x, y = v.co.x, v.co.y
            v.co.x = x * math.cos(rot) - y * math.sin(rot) + cx
            v.co.y = x * math.sin(rot) + y * math.cos(rot) + cy

    if kind == "blinds":
        step = size / 20
        k = 20
        for i in range(-k // 2, k // 2 + 1):
            bar(0, i * step, size, step * 0.57)
    elif kind == "window":
        t = size * 0.046
        for c in (-half, half * 0.42, half):
            bar(c, 0, t, size)
            bar(0, c, size, t)
    else:
        pitch, w = 0.07 * size, size * 0.07 / 6  # pattern scales with the screen
        k = int(size * 1.45 / pitch)
        for ang in (0, 90, 45, 135):
            for i in range(-k, k + 1):
                bar(0, i * pitch, size * 1.5, w, math.radians(ang))
        for axis in (0, 1):
            for sign in (1, -1):
                nrm, co = [0, 0, 0], [0, 0, 0]
                nrm[axis], co[axis] = sign, sign * half
                bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=co, plane_no=nrm, clear_outer=True)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = location
    if face is not None:
        look_at(ob, face)
    ob.visible_camera = False
    ob.visible_glossy = False
    ob.visible_transmission = False
    return ob


# ----------------------------------------------------------------------------------------------
# lights and looks
# ----------------------------------------------------------------------------------------------


def light(kind: str = "AREA", location=(0, -4, 4), target=(0, 0, 1), energy: float = 500, color=(1, 1, 1), size: float = 1.0, spot_deg: float = 30.0, haze: bool = True, only=None, name: str | None = None):
    """Add a light aimed at target. haze=False keeps it out of fog (big soft lights turn haze grey).
    only=[objects] lights just those objects (light linking): jewellery highlights without lighting the set."""
    bpy.ops.object.light_add(type=kind, location=location)
    ob = bpy.context.active_object
    if name:
        ob.name = name
    d = ob.data
    d.energy = energy
    d.color = color
    if kind == "AREA":
        d.size = size
    elif kind in ("SPOT", "POINT"):
        d.shadow_soft_size = size
    if kind == "SPOT":
        d.spot_size = math.radians(spot_deg)
        d.spot_blend = 0.3
    if kind == "SUN":
        d.angle = math.radians(size)
    if not haze:
        d.volume_factor = 0.0
    look_at(ob, target)
    if only:
        col = bpy.data.collections.new((name or "Light") + "Receivers")
        for o in only:
            for x in (o, *o.children_recursive):  # a hero's parts (chip, wordmark) get the light too
                if x.name not in col.objects:
                    col.objects.link(x)
        if hasattr(ob, "light_linking"):
            ob.light_linking.receiver_collection = col
    return ob


def world_hdri(asset_id: str | None = None, strength: float = 1.0, rotation_deg: float = 0.0, visible: bool = False, background=(0.001, 0.0012, 0.0018), res: str = "2k", path: str | None = None, reflections_only: bool = False):
    """Image-based lighting. visible=False keeps the background dark but lets metals and glass
    reflect the room (the secret to believable metal). asset_id from https://polyhaven.com/hdris,
    or path to an .exr/.hdr, or neither for Blender's bundled interior studio light.
    reflections_only=True: the room shows only in shiny surfaces and lights nothing else (moody scenes)."""
    if path is None:
        if asset_id:
            path = polyhaven_hdri(asset_id, res)
        else:
            path = os.path.join(bpy.utils.resource_path("LOCAL"), "datafiles", "studiolights", "world", "interior.exr")
    w = bpy.data.worlds.new("World")
    w.use_nodes = True
    n, l = w.node_tree.nodes, w.node_tree.links
    env = n.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(path, check_existing=True)
    mp, tc = n.new("ShaderNodeMapping"), n.new("ShaderNodeTexCoord")
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(rotation_deg))
    l.new(tc.outputs["Generated"], mp.inputs["Vector"])
    l.new(mp.outputs["Vector"], env.inputs["Vector"])
    lit = n["Background"]
    lit.inputs["Strength"].default_value = strength
    l.new(env.outputs["Color"], lit.inputs["Color"])
    if visible:
        l.new(lit.outputs["Background"], n["World Output"].inputs["Surface"])
    else:
        dark = n.new("ShaderNodeBackground")
        dark.inputs["Color"].default_value = (*background, 1)
        lp, mix = n.new("ShaderNodeLightPath"), n.new("ShaderNodeMixShader")
        if reflections_only:  # only glossy rays see the room
            l.new(lp.outputs["Is Glossy Ray"], mix.inputs["Fac"])
            l.new(dark.outputs["Background"], mix.inputs[1])
            l.new(lit.outputs["Background"], mix.inputs[2])
        else:  # camera rays see the dark colour; reflections and lighting see the room
            l.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
            l.new(lit.outputs["Background"], mix.inputs[1])
            l.new(dark.outputs["Background"], mix.inputs[2])
        l.new(mix.outputs["Shader"], n["World Output"].inputs["Surface"])
    bpy.context.scene.world = w
    return w


def world_color(color=(0.001, 0.0012, 0.0018), strength: float = 1.0):
    w = bpy.data.worlds.new("World")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*color, 1)
    bg.inputs["Strength"].default_value = strength
    bpy.context.scene.world = w
    return w


# ----------------------------------------------------------------------------------------------
# camera
# ----------------------------------------------------------------------------------------------


def camera(lens: float = 50, fstop: float = 2.0, focus=None, location=(0, -8, 1.2), target=(0, 0, 1), name: str = "Camera"):
    """A camera that always looks at a target empty (move either to frame the shot).
    Returns (camera, target_empty). Shallow focus (fstop 1.4-2.8) sells 'real lens'."""
    cd = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = location
    tgt = bpy.data.objects.new(name + "Target", None)
    bpy.context.scene.collection.objects.link(tgt)
    tgt.location = target
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis, con.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    cd.lens = lens
    cd.sensor_fit = "HORIZONTAL"  # portrait renders keep the same horizontal framing
    cd.dof.use_dof = fstop is not None
    if fstop:
        cd.dof.aperture_fstop = fstop
        cd.dof.focus_object = focus or tgt
    bpy.context.scene.camera = cam
    return cam, tgt


def _ease_all(obj) -> None:
    ad = obj.animation_data
    if not ad or not ad.action:
        return
    curves = []
    act = ad.action
    if hasattr(act, "fcurves"):
        curves = list(act.fcurves)
    else:  # layered actions (Blender 4.4+)
        for layer in getattr(act, "layers", []):
            for strip in layer.strips:
                for bag in getattr(strip, "channelbags", []):
                    curves += list(bag.fcurves)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"


def move(obj, keys: list[tuple[float, tuple]], prop: str = "location") -> None:
    """Keyframe a property along the shot. keys: [(t, value), ...] with t from 0 (first frame) to 1 (last).
    Smooth, eased, no overshoot. Use it on the camera, its target, lights, or any object."""
    n = frames()
    for t, v in keys:
        setattr(obj, prop, v)
        obj.keyframe_insert(prop, frame=1 + round(t * (n - 1)))
    _ease_all(obj)


def orbit(cam, center=(0, 0, 1), radius: float = 6.0, height: float = 1.2, start_deg: float = -110, end_deg: float = -70, steps: int = 6) -> None:
    """Arc the camera around center (angles in degrees, -90 = straight in front, looking +Y)."""
    keys = []
    for i in range(steps + 1):
        t = i / steps
        a = math.radians(start_deg + (end_deg - start_deg) * t)
        keys.append((t, (center[0] + radius * math.cos(a), center[1] + radius * math.sin(a), height)))
    move(cam, keys)


# ----------------------------------------------------------------------------------------------
# presets: a whole lighting look in one call
# ----------------------------------------------------------------------------------------------


def look_noir_haze(hero, key_from=(-6.0, 10.0, 11.0), gobo_kind: str = "mashrabiya", warmth=(1.0, 0.82, 0.58), dust_count: int = 220, scale: float = 1.0):
    """Dark, moody, light shafts through a patterned screen into thin haze; jewellery softboxes on the hero.
    Proven on gold type over black water. Tuned for a hero about 2 m tall; scale = hero height / 2 m
    (a 12 cm bottle -> scale=0.06) shrinks the whole rig, lattice, haze and dust with it."""
    k = scale
    kf = Vector(key_from) * k
    v = lambda *c: tuple(x * k for x in c)  # noqa: E731
    key = light("SPOT", tuple(kf), target=v(0.2, 0, 0.6), energy=22000 * k * k, color=warmth, size=0.02 * k, spot_deg=26, name="Key")
    gobo(gobo_kind, size=6.0 * k, location=tuple(kf * 0.45 + Vector(v(0, 0.5, 0.25))), face=tuple(kf))
    light("SPOT", v(3.5, 6.0, 5.5), target=v(0, 0, 1.1), energy=2500 * k * k, color=(1.0, 0.78, 0.5), size=0.3 * k, spot_deg=18, haze=False, name="Rim")
    light("AREA", v(0, -6, 4), target=v(0, 0, 0.8), energy=60 * k * k, size=6 * k, name="Fill")
    light("AREA", v(-2.6, -3.2, 3.4), energy=900 * k * k, size=2.2 * k, color=(1, 0.95, 0.88), haze=False, only=[hero], name="SoftL")
    light("AREA", v(3.0, -2.4, 1.6), energy=650 * k * k, size=1.4 * k, color=(1, 0.95, 0.88), haze=False, only=[hero], name="SoftR")
    # thin fog: density is per metre, so a smaller set needs proportionally denser haze to show beams
    haze(0.011 / k, center=v(0, 2, 7), size=v(40, 40, 14))
    if dust_count:
        dust(dust_count, area=(v(-4, 4), v(-6, 4), v(0.2, 4.2)), radius=0.006 * k, drift=v(0.1, 0, 0.25))
    world_hdri(None, strength=0.45, rotation_deg=140, reflections_only=True)


def look_window_morning(sun_from=(-5.0, 4.0, 4.0), warmth=(1.0, 0.84, 0.62), hdri: str | None = "art_studio", window: str = "window", haze_density: float = 0.004, sun_energy: float | None = None, room: float = 0.3):
    """Warm, low morning sun through a window across a table; soft room light for fill.
    Food, drinks, cosmetics, books, crafts. Sun power scales with distance so close tabletop and
    room-sized scenes expose the same; nudge with sun_energy. room = HDRI fill strength."""
    if sun_energy is None:
        sun_energy = 260 * Vector(sun_from).length_squared
    sun = light("SPOT", sun_from, target=(0, 0, 0.2), energy=sun_energy, color=warmth, size=0.05, spot_deg=40, name="Sun")
    gobo(window, size=3.5, location=tuple(Vector(sun_from) * 0.5), face=sun_from)
    light("AREA", (2.5, -3.0, 2.0), target=(0, 0, 0.3), energy=120, size=3.0, color=(0.85, 0.9, 1.0), haze=False, name="SkyFill")
    if haze_density:
        haze(haze_density, color=(1, 0.92, 0.8), center=(0, 0, 3), size=(20, 20, 6))
    world_hdri(hdri, strength=room, rotation_deg=200)
    return sun


def look_studio_product(hero, accent=(0.3, 0.5, 1.0), accent2=(1.0, 0.55, 0.35), backdrop=(0.006, 0.006, 0.007), hdri: str | None = None, sweep: bool = True, scale: float = 1.0):
    """Tech-launch look: near-black seamless backdrop, a soft top light, two coloured edge rims, and a
    strip light that sweeps across the hero during the shot (the 'glint' moment). Only the hero gets the
    glint and front light, so the backdrop stays dark. Devices, cards, bottles, watches, logos.
    scale: rough size of the hero in metres (1 = about a metre wide)."""
    k = scale
    cyclorama(plastic(backdrop, 0.32, "Backdrop"), width=30 * k, depth=20 * k, height=12 * k, curve=3 * k)  # glossy enough to mirror the hero
    light("AREA", (0, -0.5 * k, 4.5 * k), target=(0, 0, 0.5 * k), energy=260 * k * k, size=3.0 * k, name="Top")
    light("AREA", (-3.2 * k, 2.6 * k, 1.4 * k), target=(0, 0, 1.0 * k), energy=2200 * k * k, size=0.5 * k, color=accent, only=[hero], name="RimL")
    light("AREA", (3.2 * k, 2.6 * k, 2.0 * k), target=(0, 0, 1.0 * k), energy=1600 * k * k, size=0.5 * k, color=accent2, only=[hero], name="RimR")
    light("AREA", (0, -4.5 * k, 1.4 * k), target=(0, 0, 1.0 * k), energy=40 * k * k, size=2.5 * k, only=[hero], name="Front")
    if sweep:
        g = light("AREA", (-2.5 * k, -2.2 * k, 1.2 * k), target=(0, 0, 1.0 * k), energy=2600 * k * k, size=0.2 * k, only=[hero], name="Glint")
        g.data.shape = "RECTANGLE"
        g.data.size, g.data.size_y = 0.35 * k, 3.0 * k
        move(g, [(0.15, (-2.5 * k, -2.2 * k, 1.2 * k)), (0.85, (2.5 * k, -2.2 * k, 1.2 * k))])
        g.constraints.new("TRACK_TO").target = bpy.data.objects.get(hero.name)
    world_hdri(hdri, strength=0.25, rotation_deg=60, reflections_only=True)
