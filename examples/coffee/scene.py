# Morning coffee: a cup with crema and rising steam on a worn wooden table, a croissant beside it,
# low sun through a window. Push-in from a wide table shot to the steam.
import math

import bpy
import mashhad_kit as mk

mk.new_scene(seconds=5)

# --- table: a real scanned wood surface ---
table = mk.floor(mk.pbr("wood_table_001", res="2k", scale=0.9), size=4)

# --- cup and saucer, spun from side profiles (metres) ---
glaze = mk.ceramic((0.93, 0.9, 0.85), roughness=0.3, name="Glaze")
saucer = mk.lathe([(0.0, 0.0), (0.045, 0.0), (0.05, 0.003), (0.07, 0.007), (0.082, 0.013), (0.085, 0.015)], name="Saucer", thickness=0.004)
saucer.data.materials.append(glaze)
cup = mk.lathe([(0.0, 0.012), (0.027, 0.012), (0.03, 0.014), (0.036, 0.03), (0.042, 0.06), (0.046, 0.09), (0.047, 0.093)], name="Cup", thickness=0.0035)
cup.data.materials.append(glaze)
bpy.ops.mesh.primitive_torus_add(major_radius=0.021, minor_radius=0.0055, location=(0.064, 0, 0.056), rotation=(math.radians(90), 0, 0))
handle = bpy.context.active_object
handle.scale = (1.0, 1.0, 1.25)
handle.data.materials.append(glaze)
bpy.ops.object.shade_smooth()

# --- coffee: dark centre, golden crema at the rim ---
bpy.ops.mesh.primitive_circle_add(radius=0.0425, vertices=96, fill_type="NGON", location=(0, 0, 0.078))
coffee = bpy.context.active_object
m = bpy.data.materials.new("Coffee")
m.use_nodes = True
n, l = m.node_tree.nodes, m.node_tree.links
b = n["Principled BSDF"]
grad, ramp, noise, bump = (n.new(t) for t in ("ShaderNodeTexGradient", "ShaderNodeValToRGB", "ShaderNodeTexNoise", "ShaderNodeBump"))
grad.gradient_type = "SPHERICAL"
tc, mp = n.new("ShaderNodeTexCoord"), n.new("ShaderNodeMapping")
mp.inputs["Scale"].default_value = (1 / 0.0425,) * 3
l.new(tc.outputs["Object"], mp.inputs["Vector"])
l.new(mp.outputs["Vector"], grad.inputs["Vector"])
ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.0, (0.36, 0.18, 0.07, 1)
ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.35, (0.05, 0.02, 0.008, 1)
l.new(grad.outputs["Fac"], ramp.inputs["Fac"])
l.new(ramp.outputs["Color"], b.inputs["Base Color"])
b.inputs["Roughness"].default_value = 0.08
noise.inputs["Scale"].default_value = 900
bump.inputs["Strength"].default_value = 0.12
l.new(noise.outputs["Fac"], bump.inputs["Height"])
l.new(bump.outputs["Normal"], b.inputs["Normal"])
coffee.data.materials.append(m)

mk.steam(origin=(0, 0, 0.08), radius=0.03, height=0.3, density=22.0)

# --- croissant on a carved plate (real scans, CC0) ---
plate = mk.polyhaven_model("carved_wooden_plate")
mk.scale_to(plate, 0.24)
plate.location = (-0.21, 0.13, 0)
plate.rotation_euler.z = math.radians(20)
croissant = mk.polyhaven_model("croissant")
mk.scale_to(croissant, 0.15)
croissant.location = (-0.21, 0.13, 0.018)
croissant.rotation_euler.z = math.radians(-35)

# --- a few coffee beans: squashed spheres with a groove-free gloss, scattered ---
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1, location=(0, 0, -5))
bean = bpy.context.active_object
bean.scale = (0.0065, 0.0048, 0.0036)
bpy.ops.object.shade_smooth()
bean.data.materials.append(mk.plastic((0.09, 0.035, 0.012), 0.32, "Bean"))
mk.scatter(bean, 22, area=((0.06, 0.26), (-0.12, 0.14)), z=0.0035, seed=3, rotate=True)
for c in [o for o in bpy.data.objects if o.name.startswith(bean.name + ".")]:
    c.rotation_euler.x = c.rotation_euler.y = 0  # lie flat

# --- light: low warm sun through a window, cafe room for fill ---
mk.look_window_morning(sun_from=(-2.4, 1.5, 1.15), warmth=(1.0, 0.86, 0.7), hdri="comfy_cafe", window="window", haze_density=0.003)

# --- camera: wide table shot pushing in low to the steam ---
cam, target = mk.camera(lens=85, fstop=2.2, location=(-0.5, -1.05, 0.42), target=(-0.04, 0.02, 0.06))
mk.move(cam, [(0, (-0.5, -1.05, 0.42)), (1, (0.1, -0.64, 0.19))])
mk.move(target, [(0, (-0.04, 0.02, 0.06)), (1, (0.0, 0.0, 0.1))])
mk.save()
