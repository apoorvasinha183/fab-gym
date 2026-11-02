"""The silicon film to Ogg Theora for the cinema (docs/FAB-3D.md): Godot plays Theora, and Blender's own FFmpeg writes
it. From the SMT2020 testbed; not a real fab.

    Blender -b --factory-startup -P viz/fab3d/film_ogv.py -- IN.mp4 OUT.ogv
"""
import sys

import bpy

src, out = sys.argv[sys.argv.index("--") + 1:][:2]
sc = bpy.context.scene
se = sc.sequence_editor_create()
strips = se.strips if hasattr(se, "strips") else se.sequences
movie = strips.new_movie("film", src, channel=1, frame_start=1)
try:
    strips.new_sound("sound", src, channel=2, frame_start=1)
except Exception as e:  # a film with no sound track
    print("no sound:", e)
fps = movie.fps if hasattr(movie, "fps") else 24
sc.render.fps = int(round(fps))
sc.frame_start = 1
sc.frame_end = movie.frame_final_duration
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
sc.render.resolution_percentage = 100
if hasattr(sc.render.image_settings, "media_type"):  # Blender 5: video is its own media type
    sc.render.image_settings.media_type = "VIDEO"
sc.render.image_settings.file_format = "FFMPEG"
sc.render.ffmpeg.format = "OGG"
sc.render.ffmpeg.codec = "THEORA"
if hasattr(sc.render.ffmpeg, "constant_rate_factor"):
    sc.render.ffmpeg.constant_rate_factor = "HIGH"
sc.render.ffmpeg.audio_codec = "VORBIS"
sc.render.ffmpeg.audio_bitrate = 160
sc.render.filepath = out
bpy.ops.render.render(animation=True)
print("wrote", out, sc.frame_end, "frames at", sc.render.fps)
