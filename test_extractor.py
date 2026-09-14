"""Run with Python; all generated fixtures and results use a temporary folder."""
from pathlib import Path
import struct
import os
import tempfile
import time
import unittest
import zlib
from PIL import Image
from xpz_core import FormatError, decode_texture, extract_file, read_container, unswizzle


def fixture(path, pixels, code=0x12, width=2, height=2, name='arbitrary_asset', compress=True, xpr0=False):
    header = bytearray(2048)
    header[:4] = b'XPR0' if xpr0 else b'XPR1'
    struct.pack_into('<II', header, 4, len(header)+len(pixels), len(header))
    if xpr0:
        at = 12
        struct.pack_into('<I', header, 32, 0xffffffff)
    else:
        struct.pack_into('<I', header, 12, 1)
        struct.pack_into('<III', header, 16, 32-12, 256-12, 0)
        header[32:32+len(name.encode())+1] = name.encode()+b'\0'
        at = 256
    fmt = 0x10029 | code << 8
    if code in (0x0c, 0x0e, 0x0f, 0x06):
        fmt |= (width.bit_length()-1) << 20 | (height.bit_length()-1) << 24
    size = (width-1) | (height-1) << 12
    struct.pack_into('<5I', header, at, 0x40001, 0, 0, fmt, size)
    path.write_bytes(header + (zlib.compress(pixels) if compress else pixels))
    return path


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @unittest.skipUnless(os.environ.get('XPZ_TEST_SAMPLE') and os.environ.get('XPZ_TEST_REFERENCE'), 'Optional local sample and reference PNGs not configured')
    def test_real_sample_matches_all_original_pixels(self):
        source = Path(os.environ['XPZ_TEST_SAMPLE'])
        before = source.read_bytes()
        report = extract_file(source, self.root/'real')
        self.assertEqual((report['exported'], report['skipped']), (10, 0))
        for item in report['textures']:
            with Image.open(self.root/'real'/item['file']) as actual, Image.open(Path(os.environ['XPZ_TEST_REFERENCE'])/(item['name']+'.png')) as expected:
                self.assertEqual(actual.size, expected.size)
                self.assertEqual(actual.tobytes(), expected.tobytes())
        self.assertEqual(before, source.read_bytes())

    def test_arbitrary_names_transparency_and_path_safety(self):
        source = fixture(self.root/'unrelated.xpz', bytes([0, 0, 255, 128])*4, name='../../CON')
        report = extract_file(source, self.root/'images')
        self.assertEqual(report['exported'], 1)
        output = self.root/'images'/report['textures'][0]['file']
        self.assertEqual(output.parent, self.root/'images')
        with Image.open(output) as im:
            self.assertEqual(im.getpixel((0, 0)), (255, 0, 0, 128))
        with self.assertRaises(FileExistsError):
            extract_file(source, self.root/'images')

    def test_uncompressed_and_single_xpr0(self):
        for xpr0 in (False, True):
            source = fixture(self.root/f'{xpr0}.xpr', bytes([20, 30, 40, 255])*4, compress=False, xpr0=xpr0)
            self.assertEqual(extract_file(source, self.root/f'out{xpr0}')['exported'], 1)

    def test_dxt_formats(self):
        color = struct.pack('<HHI', 0xf800, 0, 0)
        for code, data in [(0x0c, color), (0x0e, b'\xff'*8+color), (0x0f, bytes([255, 0])+b'\0'*6+color)]:
            source = fixture(self.root/f'{code}.xpz', data, code, 4, 4)
            payload, entries, _ = read_container(source)
            im, _ = decode_texture(payload, entries[0])
            self.assertEqual(im.getpixel((3, 3)), (255, 0, 0, 255))

    def test_rectangular_swizzle(self):
        # 4x2 Morton order: (0,0),(1,0),(0,1),(1,1),(2,0),(3,0),(2,1),(3,1)
        self.assertEqual(unswizzle(bytes([0,1,4,5,2,3,6,7]),4,2,1),bytes(range(8)))
        self.assertEqual(unswizzle(bytes(range(8)),2,4,1),bytes(range(8)))

    def test_swizzled_bgra(self):
        linear = [bytes((0, 0, x*20, 255)) for x in range(8)]
        data = b''.join(linear[i] for i in (0,1,4,5,2,3,6,7))
        source = fixture(self.root/'swizzled.xpz', data, 0x06, 4, 2)
        payload, entries, _ = read_container(source)
        image, _ = decode_texture(payload, entries[0])
        self.assertEqual([image.getpixel((x,y))[0] for y in range(2) for x in range(4)], list(range(0,160,20)))

    def test_gpu_pitch_and_truncation(self):
        data = (bytes([0,255,0,255])*2 + b'\0'*56)*2
        source = fixture(self.root/'padded.xpz', data)
        payload, entries, _ = read_container(source)
        image, details = decode_texture(payload, entries[0], 'GPU pitch')
        self.assertEqual(image.getpixel((1,1)), (0,255,0,255))
        with self.assertRaisesRegex(FormatError, 'Ambiguous'):
            decode_texture(payload, entries[0])
        source.write_bytes(source.read_bytes()[:-4])
        with self.assertRaises(FormatError):
            read_container(source)

    def test_unknown_format_and_cancel(self):
        source = fixture(self.root/'unknown.xpz', b'\0'*16, 0x0b)
        report = extract_file(source, self.root/'unknown')
        self.assertEqual((report['exported'],report['skipped']),(0,1))
        self.assertIn('Unsupported pixel format', report['textures'][0]['reason'])
        report = extract_file(source, self.root/'cancel', cancelled=lambda: True)
        self.assertTrue(report['cancelled'])
        self.assertEqual(report['exported'],0)

    def test_gui_bulk_duplicate_names_and_failure_continuation(self):
        from xpz_app import App
        app = App()
        app.withdraw()
        try:
            a, b = self.root/'a', self.root/'b'
            a.mkdir(); b.mkdir()
            first = fixture(a/'same.xpz',bytes([0,0,255,255])*4)
            second = fixture(b/'same.xpz',bytes([0,255,0,255])*4)
            bad = self.root/'bad.xpz'
            bad.write_bytes(b'not a supported file')
            app.add_paths([bad, first, second, first])
            self.assertEqual(len(app.files),3)
            app.output.set(str(self.root/'bulk'))
            app.start()
            deadline = time.monotonic()+15
            while app.busy and time.monotonic()<deadline:
                app.update()
                time.sleep(0.02)
            self.assertFalse(app.busy)
            self.assertEqual(len(list(app.last_output.rglob('*.png'))),2)
            self.assertIn('1 failed files', app.status.get())
            self.assertTrue((app.last_output/'batch_report.json').exists())
        finally:
            app.destroy()


if __name__ == '__main__':
    unittest.main(verbosity=2)
