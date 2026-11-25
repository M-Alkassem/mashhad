---
name: mashhad
description: Directs and renders cinematic 3D scroll scenes for a website's landing page with Blender, locally and free (no AI video, no credits), then wires them into the site as a scroll-driven hero. Use when someone wants a 3D hero, a cinematic or "Apple-style" scroll animation, a product fly-through, an animated 3D logo, a "Higgsfield-style" or "award-winning" landing page, or asks to make their landing page look premium with 3D or motion.
---

# Mashhad (مشهد, "scene"): cinematic 3D scroll heroes

You are the director. You design a short camera move through a 3D scene that fits the brand,
build it in Blender with the kit, look at the frames like a cinematographer, fix what is weak,
render it for desktop and phones, and drop it into the site as a scroll-driven film.

Everything runs on the user's computer. Blender renders; nothing is uploaded.
Scripts live in this skill's folder: `scripts/mashhad.py` (the CLI), `kit/mashhad_kit.py`
(scene building blocks), `engine/mashhad-film.js` (the web player). Call the CLI with its full path.

## 0. Check the tools (once)

```bash
python3 <skill>/scripts/mashhad.py doctor
```

Needs Blender 4.2+ (free, https://www.blender.org/download/, about 400 MB). If it is missing, tell
the user what it is and where to get it; do not install it without their OK. ffmpeg is optional
(contact sheets, videos). First use of a Poly Haven asset downloads it (a few MB, CC0) into
`~/.cache/mashhad`.

## 1. Understand the brand, pitch scenes

Read the site first: the product, the audience, colours, fonts, the hero copy. Then pitch
**2-3 scene ideas** in plain words, each with a one-line shot ("we start wide on a wooden counter
in morning sun and push in to the steam rising from the cup"). Say which subject is real
(their logo SVG, a 3D model they have, a Poly Haven scan, or something you build from shapes).
Let them pick before you build.

What looks great: products, logos and type, objects on a table, architecture, abstract
materials (glass, metal, liquid surfaces, light). What does not: people, faces, animals, cloth
and fluid simulations. Steer away from those and say why.

## 2. Write the scene

Put it in the user's project, e.g. `mashhad/hero/scene.py`. Short, readable, top to bottom:

```python
import mashhad_kit as mk
mk.new_scene(seconds=5)                       # 120 frames at 24 fps; 4-6 s is right for a hero
logo = mk.svg_logo("logo.svg", width=2.4)      # or mk.polyhaven_model(...), mk.import_model(...), mk.lathe(...)
mk.assign(logo, mk.metal("gold"))
mk.floor(mk.dark_water())
mk.look_noir_haze(logo)                        # or look_window_morning(...), look_studio_product(...)
cam, target = mk.camera(lens=50, fstop=1.4, location=(-3, -10, 0.5), target=(0, 0, 0.8))
mk.move(cam, [(0, (-3, -10, 0.5)), (1, (0.7, -6.3, 1.3))])   # t goes 0 -> 1 over the shot
mk.move(target, [(0, (-0.6, 0, 0.7)), (1, (0.1, 0, 1.1))])
mk.save()
```

Then build it and look:

```bash
python3 <skill>/scripts/mashhad.py build mashhad/hero/scene.py
python3 <skill>/scripts/mashhad.py preview mashhad/hero/build/scene.blend      # 5 frames, seconds
python3 <skill>/scripts/mashhad.py preview mashhad/hero/build/scene.blend --aspect portrait
python3 <skill>/scripts/mashhad.py preview mashhad/hero/build/scene.blend --frames 120 --size final   # check labels, fine detail
```

The very first Blender launch after installing can take minutes while macOS verifies the app; later
launches take about a second. Progress prints per frame, and on macOS the CLI keeps the computer
awake while Blender runs.

**Always open the contact sheet image the preview prints and judge it** (section 4). Iterate:
edit scene.py, build, preview. Expect 4-8 rounds; each takes seconds. Look at the actual pixels,
never assume a change worked.

## 3. The kit (kit/mashhad_kit.py; read it for every parameter)

| Need | Call |
|---|---|
| Scene | `new_scene(seconds, fps)`, `save()`, `frames()` |
| Their logo / wordmark | `svg_logo(path, width, depth, bevel)` (stands on z=0, faces the camera) |
| Latin text | `text(body, size, depth, font=path.ttf)` |
| Their 3D model | `import_model(path.glb/.gltf/.obj/.fbx/.usdz)`, then `scale_to(root, metres)` |
| Real scanned objects | `polyhaven_model(id)` (polyhaven.com/models: croissant, tea_set_01, brass_vase_01, …) |
| Real surfaces | `pbr(id, scale=metres)` (polyhaven.com/textures: wood_table_001, marble_01, concrete_floor_02, …) |
| Shapes from code | `lathe([(r, z), …], thickness)` cups, bottles, vases · `rounded_panel(w, h, thickness, radius)` cards, phones, tablets, signs · `rounded_box(size, radius)` chunky devices, plinths · `cyclorama()` studio backdrop · `floor()` · `scatter(obj, n, area)` |
| Materials | `metal(kind, brushed=False)` gold/silver/copper/brass/titanium/black_chrome · `glass()` · `ceramic()` · `plastic()` · `liquid()` · `emission()` · `dark_water()` |
| Atmosphere | `haze(density)` · `dust(count)` · `steam(origin, radius, height, density)` · `gobo(kind, location, face)` mashrabiya/blinds/window |
| Light | `light(kind, location, target, energy, size, haze=False, only=[objs])` · `world_hdri(id or None, strength, reflections_only)` · `world_color()` |
| Looks (whole rigs) | `look_noir_haze(hero, scale)` gold/dark/shafts (scale = hero height / 2 m) · `look_window_morning(sun_from, hdri)` food, drinks, crafts · `look_studio_product(hero, accent, accent2, scale)` tech, devices, cards (with a glint sweep) |
| Camera | `camera(lens, fstop, location, target)` → (cam, target) · `move(obj, [(t, value), …])` · `orbit(cam, center, radius, start_deg, end_deg)` |
| Helpers | `place_on_floor(obj, z)`, `fit(obj, size)`, `bounds(obj)`, `look_at(obj, target)`, `assign(obj, material)` |

Plain Blender Python (`bpy`) works alongside the kit whenever you need something it doesn't have.

## 4. Director's eye: judge every sheet against this

1. **Is the subject lit?** Shadows across the hero (a window bar, a lattice) kill it. Move the gobo
   or the light so an open gap lights the subject.
2. **Exposure.** No blown whites on the hero, no muddy greys. The look presets scale sun power by
   distance; nudge `sun_energy`/`energy` by 1.5x steps, not 10x.
3. **Grey veil = haze lit by a big soft light.** Give soft lights `haze=False`. Keep haze density
   0.003-0.02.
4. **Metal looks brown or flat = nothing to reflect.** Add `world_hdri(..., reflections_only=True)`
   and softboxes with `only=[hero]` (they light the hero, not the set).
5. **Steam/smoke is a solid column = too dense.** Wisps, not pillars; backlight it.
6. **Framing.** Start wide enough to read the whole scene; end close but never cropping the hero's
   key part (rim of the cup, top of the logo). Keep the hero in focus (`fstop` 1.4-2.8 on the target).
7. **One move per shot**, eased, slow. Push-in, gentle orbit, crane up. No spins, no snapping.
8. **Portrait.** Check `--aspect portrait`: the hero must fit the narrow frame (`--portrait-zoom 1.0`
   if it crops, up to 1.4 if it looks lost).
9. **Black products need edges.** Dark metal or glass disappears on a dark set; rim lights with
   `only=[hero]` draw its outline in brand colours without lighting the floor.
10. **Real-world scale.** Model in metres (a cup is 0.09 m tall). Lights, focus and haze all assume it.
11. **Glass products.** `glass()` in EEVEE does not show up in screen-space reflections, so a glass
    bottle on `dark_water()` floats with no reflection. Stand glass on an opaque plinth or slab (stone,
    black acrylic) whose reflection grounds it. Labels and caps on glass: separate objects just outside
    the glass surface; don't switch glass to dithered (it smears what's in front). For true glass
    refraction and caustics in a hero still, use `--engine cycles` on that one frame.
12. **Focus at product scale.** Under about 1 m from the subject, f/2.8 is razor thin: aim the camera
    target at the face that matters (the label, not the object's centre) and use f/4-f/8 for small products.
13. **Seams.** Only one scene per film for now; cut between films with page sections.

Ask the user to look at the sheet too once it is good; taste is theirs.

## 5. Render, pack, put it in the site

```bash
python3 <skill>/scripts/mashhad.py render mashhad/hero/build/scene.blend            # landscape + portrait
python3 <skill>/scripts/mashhad.py pack mashhad/hero/build public/mashhad/hero       # site's static folder
```

Rendering takes minutes (EEVEE, about 1-3 s a frame on a laptop); run it in the background and
tell the user. `--engine cycles` is photoreal but 50-100x slower: only for a single hero still.
On thin laptops without fans, render one thing at a time.

`pack` writes JPEG frames, `manifest.json`, `poster.jpg` and `mashhad-film.js` (no dependencies).
Use it in any page:

```html
<script type="module" src="/mashhad/hero/mashhad-film.js"></script>
<mashhad-film src="/mashhad/hero" length="400">
  <h1 data-from="0" data-to="0.3" style="top:14vh;left:0;right:0;text-align:center">Headline</h1>
  <a data-from="0.75" data-to="1" style="bottom:12vh;left:50%;translate:-50%" href="#start">Get started</a>
</mashhad-film>
```

React/Next: import the script once (e.g. `useEffect(() => { import("/mashhad/hero/mashhad-film.js") }, [])`
or a `<Script type="module">`) and render `<mashhad-film src=... length=...>` as JSX; TypeScript may
need `declare namespace JSX { interface IntrinsicElements { "mashhad-film": any } }`.

Children with `data-from`/`data-to` (0..1 scroll progress) fade in and out; position them with the
site's own CSS. Put a soft gradient behind copy so it reads over bright frames, e.g.
`mashhad-film .mf-layer { background: linear-gradient(rgba(0,0,0,.5), transparent 32%, transparent 62%, rgba(0,0,0,.55)) }`. `--mashhad-progress` is set on the element for custom effects. Reduced-motion
users see a still frame.

Finally open the page (browser preview if available), scroll it top to bottom, check the copy
appears at the right moments on desktop and phone width, and show the user.

## Text in any language

Blender's own text cannot join Arabic, Persian, Urdu, Hebrew or Indic scripts correctly. Shape the
text to an SVG first (for Arabic, the free Khatt tool: github.com/M-Alkassem/khatt, or any vector
editor's "convert text to outlines"), then `svg_logo()` it.
