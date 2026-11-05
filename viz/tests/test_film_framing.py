"""Cinema captions and actual conversion framing. Set BLENDER to run the short encode checks."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from viz.fab3d.prepare_film import captions, digest, prepare

ROOT = Path(__file__).resolve().parents[2]


class Captions(unittest.TestCase):
    def test_multiline_unicode_and_millisecond_timing(self):
        srt = '1\r\n00:01:02,375 --> 00:01:05,000\r\n<b>Someone must act.</b>\r\nRodion’s choice &amp; consequence.\r\n'
        self.assertEqual(captions(srt), [{"start": 62.375, "end": 65.0,
            "text": "Someone must act.\nRodion’s choice & consequence."}])

    def test_empty_subtitle_stream(self):
        self.assertEqual(captions(""), [])


@unittest.skipUnless(os.environ.get("BLENDER"), "Set BLENDER to verify actual video framing")
class Conversion(unittest.TestCase):
    def test_all_four_source_edges_survive_hd_portrait_and_widescreen(self):
        with tempfile.TemporaryDirectory(prefix="film-framing-") as tmp:
            for width, height in [(1920, 1080), (1080, 1920), (2048, 858)]:
                with self.subTest(size=(width, height)):
                    source, out = Path(tmp) / 'source.mp4', Path(tmp) / 'out.ogv'
                    border = 80
                    graph = (f'color=black:s={width}x{height}:r=24:d=0.5,'
                        f'drawbox=x=0:y=0:w={border}:h=ih:c=red:t=fill,'
                        f'drawbox=x=iw-{border}:y=0:w={border}:h=ih:c=lime:t=fill,'
                        f'drawbox=x=0:y=0:w=iw:h={border}:c=blue:t=fill,'
                        f'drawbox=x=0:y=ih-{border}:w=iw:h={border}:c=yellow:t=fill')
                    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',graph,
                        '-c:v','libx264','-threads','2','-pix_fmt','yuv420p',str(source)],check=True)
                    metadata = prepare(source, out, Path(os.environ['BLENDER']))
                    self.assertEqual(metadata['source_sha256'], digest(source))
                    written = out.stat().st_mtime_ns
                    prepare(source, out, Path(os.environ['BLENDER']))
                    self.assertEqual(out.stat().st_mtime_ns, written, "unchanged movies need no re-encode")
                    rgb = subprocess.check_output(['ffmpeg','-v','error','-i',str(out),
                        '-frames:v','1','-threads','2','-pix_fmt','rgb24','-f','rawvideo','-'])
                    scale = min(1280/width,720/height)
                    left, top = (1280-width*scale)/2, (720-height*scale)/2
                    points=[(left+border*scale/2,360),(1280-left-border*scale/2,360),
                            (640,top+border*scale/2),(640,720-top-border*scale/2)]
                    colors=[]
                    for x,y in points:
                        offset=(int(y)*1280+int(x))*3
                        colors.append(tuple(rgb[offset:offset+3]))
                    red,green,blue,yellow=colors
                    self.assertTrue(red[0]>100 and red[0]>red[1]*2, colors)
                    self.assertTrue(green[1]>100 and green[1]>green[0]*2, colors)
                    self.assertTrue(blue[2]>100 and blue[2]>blue[0]*2, colors)
                    self.assertTrue(yellow[0]>100 and yellow[1]>100 and yellow[2]<80, colors)


if __name__ == '__main__':
    unittest.main()
