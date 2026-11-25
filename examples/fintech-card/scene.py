# Fintech launch: a brushed black metal card with a gold chip and an embossed wordmark turns to face
# the viewer in a dark studio, rim-lit in brand colours. Everything is built from code.
import math

import bpy
import mashhad_kit as mk

mk.new_scene(seconds=5)

# card at 20x real size (85.6 x 54 mm) so the studio lights and focus read like a product film
W, H, T = 1.712, 1.08, 0.022
card = mk.rounded_panel(W, H, T, radius=0.1, name="Card")
card.location = (0, 0, 1.0)
body = mk.metal((0.035, 0.035, 0.04), roughness=0.3, name="BlackMetal")
# brushed finish: stretch the roughness noise along the card
for nd in body.node_tree.nodes:
    if nd.bl_idname == "ShaderNodeTexNoise":
        nd.inputs["Scale"].default_value = 60
        mp = body.node_tree.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1, 1, 40)  # streaks run along the card
        tc = body.node_tree.nodes.new("ShaderNodeTexCoord")
        body.node_tree.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        body.node_tree.links.new(mp.outputs["Vector"], nd.inputs["Vector"])
card.data.materials.append(body)

chip = mk.rounded_box((0.2, 0.012, 0.16), radius=0.02, name="Chip")
chip.parent = card
chip.location = (-0.52, -T / 2 - 0.002, 0.08)
chip.data.materials.append(mk.metal("gold", roughness=0.16))

word = mk.text("nova", size=0.2, depth=0.006, bevel=0.002, name="Wordmark")
word.parent = card
word.rotation_euler = (math.radians(90), 0, 0)
word.location = (0.46, -T / 2 - 0.004, -0.38)
word.data.materials.append(mk.metal("silver", roughness=0.12))

mk.look_studio_product(card, accent=(0.3, 0.5, 1.0))

# the card turns from a steep angle to face the camera, settling with a slight tilt
mk.move(card, [(0, (math.radians(-6), 0, math.radians(-62))), (1, (math.radians(4), 0, math.radians(-12)))], prop="rotation_euler")
mk.move(card, [(0, (0, 0.4, 1.0)), (1, (0, 0, 1.05))])

cam, target = mk.camera(lens=60, fstop=2.0, location=(-1.6, -6.2, 1.5), target=(0, 0, 1.0))
mk.move(cam, [(0, (-1.6, -6.2, 1.5)), (1, (0.5, -4.6, 1.2))])
mk.save()
