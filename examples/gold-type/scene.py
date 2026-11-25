# Gold calligraphy over black water, light falling through a mashrabiya into haze.
import os

import mashhad_kit as mk

HERE = os.path.dirname(os.path.abspath(__file__))
mk.new_scene(seconds=5)

word = mk.svg_logo(os.path.join(HERE, "khatt.svg"), width=2.4, depth=0.07)
mk.place_on_floor(word, 0.06)
mk.assign(word, mk.metal("gold", roughness=0.19))
mk.floor(mk.dark_water())

mk.look_noir_haze(word)

cam, target = mk.camera(lens=50, fstop=1.4, location=(-3.2, -10.5, 0.45), target=(-0.6, 0, 0.7))
mk.move(cam, [(0, (-3.2, -10.5, 0.45)), (1, (0.7, -6.3, 1.3))])
mk.move(target, [(0, (-0.6, 0, 0.7)), (1, (0.1, 0, 1.1))])
mk.save()
