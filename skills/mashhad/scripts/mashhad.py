#!/usr/bin/env python3
"""mashhad: build, preview, render and pack cinematic Blender scenes for a landing page.

  python3 mashhad.py doctor                          check Blender and ffmpeg
  python3 mashhad.py build   scene.py                run a scene script -> scene.blend
  python3 mashhad.py preview scene.blend             fast look at a few frames + contact sheet
  python3 mashhad.py render  scene.blend             every frame, landscape and portrait
  python3 mashhad.py sheet   DIR                     contact sheet of rendered frames
  python3 mashhad.py pack    BUILD_DIR SITE_DIR      web frames + manifest + player for the site

Output goes in a build/ folder next to the scene. Nothing is uploaded anywhere.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent / "kit"
ENGINE = HERE.parent / "engine"


# ---------------------------------------------------------------------------------- tools


def find_blender() -> str | None:
    env = os.environ.get("MASHHAD_BLENDER")
    if env and Path(env).exists():
        return env
    candidates = [
        shutil.which("blender"),
        "/Applications/Blender.app/Contents/MacOS/Blender",
        str(Path.home() / "Applications/Blender.app/Contents/MacOS/Blender"),
        "/snap/bin/blender",
        "/usr/bin/blender",
    ]
    candidates += sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True)
    return next((c for c in candidates if c and Path(c).exists()), None)


def need_blender() -> str:
    b = find_blender()
    if not b:
        sys.exit(
            "Blender not found. Install it from https://www.blender.org/download/ (free, 4.2 or newer), "
            "or set MASHHAD_BLENDER to its executable."
        )
    return b


def ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def run_blender(args: list[str], quiet: bool = True, total: int | None = None) -> str:
    cmd = [need_blender(), "-b", *args]
    # macOS can throttle or nap a long background render; keep the machine awake while Blender runs
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        cmd = ["caffeinate", "-i", *cmd]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines, done, t0 = [], 0, time.time()
    for line in p.stdout:  # stream so long renders show progress instead of looking hung
        lines.append(line.rstrip("\n"))
        if "Saved:" in line:
            done += 1
            el = time.time() - t0
            eta = f", ~{el / done * (total - done):.0f}s left" if total and done < total else ""
            print(f"  frame {done}{'/' + str(total) if total else ''} ({el:.0f}s{eta})", flush=True)
    p.wait()
    out = "\n".join(lines)
    errors = [l for l in out.splitlines() if "Error" in l or "Traceback" in l or l.startswith("  File ")]
    if p.returncode or any("Traceback" in l for l in errors):
        print(out[-6000:])
        sys.exit(f"Blender failed (exit {p.returncode}).")
    if not quiet:
        print(out)
    for l in out.splitlines():
        if l.startswith(("MASHHAD_", "Warning")):
            print(l)
    return out


# ---------------------------------------------------------------------------------- commands


def cmd_doctor(_a) -> None:
    b = find_blender()
    print("blender:", b or "MISSING (https://www.blender.org/download/)")
    print("         (the first launch after installing can take minutes while macOS verifies the app)")
    if b:
        v = subprocess.run([b, "--version"], capture_output=True, text=True).stdout.splitlines()
        print("  ", v[0] if v else "?")
    print("ffmpeg: ", ffmpeg() or "missing (optional: contact sheets and faster packing)")
    print("kit:    ", KIT / "mashhad_kit.py")
    print("cache:  ", os.environ.get("MASHHAD_CACHE", Path.home() / ".cache/mashhad/polyhaven"))
    if not b:
        sys.exit(1)


def build_dir_for(path: Path) -> Path:
    parent = path.resolve().parent
    d = parent if parent.name == "build" else parent / "build"
    d.mkdir(exist_ok=True)
    return d


def cmd_build(a) -> None:
    scene = Path(a.scene).resolve()
    out = Path(a.out).resolve() if a.out else build_dir_for(scene) / (scene.stem + ".blend")
    t = time.time()
    # the scene script imports the kit; PYTHONPATH points Blender's Python at it
    run_blender(["--factory-startup", "--python-expr", f"import sys; sys.path.insert(0, {str(KIT)!r})", "-P", str(scene), "--", str(out)])
    print(f"built {out} in {time.time() - t:.0f}s")


def _render(blend: Path, out_dir: Path, frames: list[int] | None, aspect: str, engine: str, samples: int, size: str, zoom: float | None, total: int | None = None) -> float:
    out_dir.mkdir(parents=True, exist_ok=True)
    opts = {"out": str(out_dir) + "/", "aspect": aspect, "engine": engine, "samples": samples, "size": size}
    if zoom:
        opts["portrait_zoom"] = zoom
    fargs = [x for f in frames for x in ("-f", str(f))] if frames else ["-a"]
    t = time.time()
    run_blender([str(blend), "-P", str(HERE / "blender_render.py"), *fargs, "--", json.dumps(opts)], total=len(frames) if frames else total)
    return time.time() - t


def _frame_count(blend: Path) -> int:
    out = run_blender([str(blend), "--python-expr", "import bpy; print('MASHHAD_FRAMES', bpy.context.scene.frame_end)"])
    for l in out.splitlines():
        if l.startswith("MASHHAD_FRAMES"):
            return int(l.split()[1])
    return 120


def sheet(src: Path, out: Path, cols: int = 3, every: int | None = None) -> Path | None:
    files = sorted(src.glob("*.png")) or sorted(src.glob("*.jpg"))
    if not files or not ffmpeg():
        return None
    picks = files if every is None else files[::every]
    picks = picks[:12]
    rows = (len(picks) + cols - 1) // cols
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p}'\n" for p in picks))
    label = "drawtext=text='%{n}':x=8:y=8:fontcolor=white:fontsize=18:box=1:boxcolor=black@0.5,"
    out.unlink(missing_ok=True)
    for filt in (f"scale=640:-2,{label}tile={cols}x{rows}", f"scale=640:-2,tile={cols}x{rows}"):  # drawtext needs freetype
        subprocess.run([ffmpeg(), "-loglevel", "quiet", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", filt, "-frames:v", "1", str(out)], check=False)
        if out.exists():
            break
    lst.unlink(missing_ok=True)
    return out if out.exists() else None


def cmd_preview(a) -> None:
    blend = Path(a.blend).resolve()
    n = _frame_count(blend)
    picks = [int(x) for x in a.frames.split(",")] if a.frames else sorted({1, round(n * 0.25), round(n * 0.5), round(n * 0.75), n})
    out = build_dir_for(blend) / "preview" / a.aspect
    shutil.rmtree(out, ignore_errors=True)
    s = _render(blend, out, picks, a.aspect, "eevee", a.samples, a.size, a.portrait_zoom)
    files = sorted(out.glob("*.png"))
    # one row for up to 5 frames (no empty black tiles), otherwise rows of 3
    sh = sheet(out, out.parent / f"sheet-{a.aspect}.png", cols=len(files) if len(files) <= 5 else 3)
    print(f"preview: {len(files)} frames in {s:.0f}s -> {out}")
    if sh:
        print(f"sheet:   {sh}")


def cmd_render(a) -> None:
    blend = Path(a.blend).resolve()
    aspects = ["landscape", "portrait"] if a.aspect == "both" else [a.aspect]
    for asp in aspects:
        out = build_dir_for(blend) / "frames" / asp
        shutil.rmtree(out, ignore_errors=True)
        s = _render(blend, out, None, asp, a.engine, a.samples, a.size, a.portrait_zoom, total=_frame_count(blend))
        n = len(list(out.glob("*.png")))
        print(f"{asp}: {n} frames in {s:.0f}s ({s / max(n, 1):.1f}s/frame) -> {out}")
        sh = sheet(out, out.parent / f"sheet-{asp}.png", every=max(1, n // 9))
        if sh:
            print(f"sheet: {sh}")
        if ffmpeg():
            mp4 = out.parent / f"{asp}.mp4"
            fps = 24
            subprocess.run([ffmpeg(), "-loglevel", "error", "-y", "-framerate", str(fps), "-i", str(out / "%04d.png"),
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(mp4)], check=False)
            if mp4.exists():
                print(f"video: {mp4}")


def cmd_sheet(a) -> None:
    src = Path(a.dir).resolve()
    sh = sheet(src, src.parent / f"sheet-{src.name}.png", every=a.every)
    print(sh or "no frames, or ffmpeg missing")


def _to_jpg(src: Path, dst: Path, quality: int) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    if ffmpeg():
        q = max(2, min(31, round(31 - quality * 0.29)))  # 82 -> ~7
        subprocess.run([ffmpeg(), "-loglevel", "error", "-y", "-i", str(src / "%04d.png"), "-q:v", str(q), "-start_number", "1", str(dst / "%04d.jpg")], check=True)
        return
    expr = (
        "import bpy,glob,os;"
        f"src={str(src)!r};dst={str(dst)!r};"
        "s=bpy.context.scene;s.render.image_settings.file_format='JPEG';"
        f"s.render.image_settings.quality={quality};"
        "[(lambda im:(im.save_render(os.path.join(dst,os.path.basename(f)[:-4]+'.jpg'),scene=s),bpy.data.images.remove(im)))(bpy.data.images.load(f)) for f in sorted(glob.glob(src+'/*.png'))]"
    )
    run_blender(["--factory-startup", "--python-expr", expr])


def cmd_pack(a) -> None:
    build = Path(a.build).resolve()
    site = Path(a.site).resolve()
    site.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "fps": 24, "variants": {}}
    for asp in ("landscape", "portrait"):
        src = build / "frames" / asp
        pngs = sorted(src.glob("*.png"))
        if not pngs:
            continue
        dst = site / asp
        shutil.rmtree(dst, ignore_errors=True)
        _to_jpg(src, dst, a.quality)
        n = len(list(dst.glob("*.jpg")))
        w, h = (1280, 720) if asp == "landscape" else (720, 1280)
        try:
            import struct

            with open(pngs[0], "rb") as f:
                f.read(16)
                w, h = struct.unpack(">II", f.read(8))
        except Exception:
            pass
        manifest["variants"][asp] = {"frames": n, "width": w, "height": h, "path": f"{asp}/{{n}}.jpg", "pad": 4}
        if asp == "landscape":
            shutil.copy(dst / "0001.jpg", site / "poster.jpg")
    if not manifest["variants"]:
        sys.exit(f"no rendered frames under {build / 'frames'}; run render first")
    (site / "manifest.json").write_text(json.dumps(manifest, indent=2))
    shutil.copy(ENGINE / "mashhad-film.js", site / "mashhad-film.js")
    size = sum(f.stat().st_size for f in site.rglob("*") if f.is_file())
    parts = ", ".join(f"{k} {v['frames']} frames" for k, v in manifest["variants"].items())
    print(f"packed -> {site} ({size / 1e6:.1f} MB): {parts}")


def main() -> None:
    p = argparse.ArgumentParser(prog="mashhad", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    b = sub.add_parser("build")
    b.add_argument("scene")
    b.add_argument("-o", "--out")
    b.set_defaults(fn=cmd_build)
    for name, fn in (("preview", cmd_preview), ("render", cmd_render)):
        r = sub.add_parser(name)
        r.add_argument("blend")
        r.add_argument("--aspect", default="landscape" if name == "preview" else "both", choices=["landscape", "portrait", "both"] if name == "render" else ["landscape", "portrait"])
        r.add_argument("--samples", type=int, default=16 if name == "preview" else 48)
        r.add_argument("--portrait-zoom", type=float, default=None)
        if name == "preview":
            r.add_argument("--frames", help="comma-separated frame numbers")
            r.add_argument("--size", default="preview", choices=["preview", "draft", "final"], help="check labels and fine detail at draft/final size")
        else:
            r.add_argument("--engine", default="eevee", choices=["eevee", "cycles"])
            r.add_argument("--size", default="final", choices=["draft", "final", "hd"])
        r.set_defaults(fn=fn)
    s = sub.add_parser("sheet")
    s.add_argument("dir")
    s.add_argument("--every", type=int, default=None)
    s.set_defaults(fn=cmd_sheet)
    k = sub.add_parser("pack")
    k.add_argument("build", help="the build/ folder next to the scene")
    k.add_argument("site", help="where the site serves it from, e.g. public/mashhad/hero")
    k.add_argument("--quality", type=int, default=82)
    k.set_defaults(fn=cmd_pack)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
