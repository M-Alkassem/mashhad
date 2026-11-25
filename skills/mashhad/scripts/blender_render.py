# Runs inside Blender: apply render settings to a saved scene, then Blender renders the frames.
# Called by mashhad.py; arguments come after "--" as JSON.
import json
import sys

import bpy

opts = json.loads(sys.argv[sys.argv.index("--") + 1])
sc = bpy.context.scene

# --- frame size: landscape 16:9 or portrait 9:16 with the same horizontal framing ---
long_side = {"preview": 640, "draft": 960, "final": 1280, "hd": 1920}[opts.get("size", "final")]
if opts.get("aspect") == "portrait":
    sc.render.resolution_x, sc.render.resolution_y = round(long_side * 9 / 16 / 2) * 2, long_side
    cam = sc.camera
    if cam:
        # same horizontal view as landscape (the subject fits the narrow screen), pushed in a little
        # so it doesn't look lost; override per scene with portrait_zoom (1.0 = no push)
        cam.data.sensor_fit = "HORIZONTAL"
        cam.data.lens *= float(opts.get("portrait_zoom", 1.2))
else:
    sc.render.resolution_x, sc.render.resolution_y = long_side, round(long_side * 9 / 16 / 2) * 2
sc.render.resolution_percentage = 100
sc.render.filepath = opts["out"]
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_depth = "8"

engine = opts.get("engine", "eevee")
samples = int(opts.get("samples", 48))
if engine == "cycles":
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            if any(d.type == backend for d in prefs.devices):
                break
        except TypeError:
            continue
    for d in prefs.devices:
        d.use = True
    sc.cycles.device = "GPU" if any(d.type != "CPU" and d.use for d in prefs.devices) else "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8
    sc.cycles.volume_bounces = 1
    sc.cycles.volume_step_rate = 2.0
    sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
else:
    names = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in names else "BLENDER_EEVEE"
    ee = sc.eevee
    ee.taa_render_samples = samples
    for attr, val in [
        ("use_shadows", True),
        ("use_volumetric_shadows", True),
        ("volumetric_tile_size", "4"),
        ("volumetric_samples", 96),
        ("volumetric_shadow_samples", 32),
        ("use_raytracing", True),
        ("ray_tracing_method", "SCREEN"),
        ("use_fast_gi", True),
        ("shadow_ray_count", 2),
        ("shadow_step_count", 8),
    ]:
        if hasattr(ee, attr):
            try:
                setattr(ee, attr, val)
            except (TypeError, ValueError) as e:
                print("MASHHAD_SKIP", attr, e)
    if hasattr(ee, "ray_tracing_options"):
        ee.ray_tracing_options.resolution_scale = "1"
print("MASHHAD_RENDER", sc.render.engine, sc.render.resolution_x, "x", sc.render.resolution_y, "samples", samples)
