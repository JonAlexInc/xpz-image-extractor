"""Xbox XPR texture extraction. No filename or content fingerprint restrictions.

Supports named XPR1 tables with offsets relative to byte 12, plus single-texture
XPR0. This is not a universal parser for every game using the XPZ extension.
"""
from pathlib import Path
import hashlib
import io
import json
import re
import struct
import zlib
from PIL import Image

MAX_BYTES = 256 * 1024 * 1024
LINEAR = {0x10: 0x02, 0x11: 0x05, 0x12: 0x06, 0x13: 0x00,
          0x1C: 0x03, 0x1D: 0x04, 0x1E: 0x07, 0x1F: 0x19,
          0x20: 0x1A, 0x3F: 0x3A}
BPP = {0x00: 1, 0x02: 2, 0x03: 2, 0x04: 2, 0x05: 2,
       0x06: 4, 0x07: 4, 0x19: 1, 0x1A: 2, 0x3A: 4}


class FormatError(ValueError):
    pass


def safe_name(value):
    # Names in archives are data, never paths. Prefix also avoids Windows devices.
    return re.sub(r'[^a-zA-Z0-9_.-]+', '_', value).strip(' ._')[:100] or 'texture'


def read_container(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise FormatError('File exceeds the 256 MB limit.')
    packed = path.read_bytes()
    if len(packed) < 32 or packed[:4] not in (b'XPR0', b'XPR1'):
        raise FormatError('Unsupported container: expected an Xbox XPR0 or XPR1 header.')
    total, header = struct.unpack_from('<II', packed, 4)
    if not 32 <= header <= len(packed) or not header < total <= MAX_BYTES:
        raise FormatError('Invalid container sizes or expanded size exceeds 256 MB.')
    raw = packed[header:]
    # zlib header test; never attempt unbounded decompression.
    compressed = len(raw) >= 2 and raw[0] & 15 == 8 and raw[0] >> 4 <= 7 and int.from_bytes(raw[:2], 'big') % 31 == 0
    if compressed:
        try:
            decoder = zlib.decompressobj()
            payload = decoder.decompress(raw, total - header + 1)
            if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data or len(payload) != total - header:
                raise FormatError('Compressed payload does not match the declared size.')
        except zlib.error as exc:
            raise FormatError(f'Invalid zlib stream: {exc}') from exc
    else:
        payload = raw
        if len(payload) != total - header:
            raise FormatError('Unknown compression or truncated payload; zlib and uncompressed data are supported.')
    entries = []
    if packed[:4] == b'XPR1':
        count = struct.unpack_from('<I', packed, 12)[0]
        if not 1 <= count <= 10000 or 16 + count * 12 > header:
            raise FormatError('Unsupported or invalid XPR1 resource table.')
        for i in range(count):
            name_at, record_at, _ = struct.unpack_from('<III', packed, 16 + i * 12)
            name_at += 12
            record_at += 12
            if not 16 + count * 12 <= name_at < header or not 16 + count * 12 <= record_at <= header - 20:
                raise FormatError('Resource table points outside the header.')
            end = packed.find(b'\0', name_at, header)
            if end < 0:
                raise FormatError('Resource name is not terminated.')
            name = packed[name_at:end].decode('utf-8', errors='replace')
            entries.append(dict(name=name, values=struct.unpack_from('<5I', packed, record_at)))
    else:
        # Multi-resource XPR0 layouts have no names and vary between producers.
        if header > 32 and struct.unpack_from('<I', packed, 32)[0] != 0xffffffff:
            raise FormatError('Multi-resource XPR0 layout is not supported yet.')
        entries.append(dict(name=path.stem, values=struct.unpack_from('<5I', packed, 12)))
    offsets = sorted(set(e['values'][1] for e in entries if e['values'][1] < len(payload)))
    for entry in entries:
        offset = entry['values'][1]
        entry['end'] = next((n for n in offsets if n > offset), len(payload))
    return payload, entries, dict(container=packed[:4].decode(), compression='zlib' if compressed else 'none', sha256=hashlib.sha256(packed).hexdigest())


def unswizzle(data, width, height, bpp):
    # Interleave only bits that exist in each axis (rectangular Morton layout).
    def axis_offsets(length, other, x_axis):
        result = []
        for value in range(length):
            target = shift = 0
            bit = 1
            while bit < max(length, other):
                if bit < (length if x_axis else other):
                    if x_axis and value & bit:
                        target |= 1 << shift
                    shift += 1
                if bit < (other if x_axis else length):
                    if not x_axis and value & bit:
                        target |= 1 << shift
                    shift += 1
                bit <<= 1
            result.append(target)
        return result
    xs = axis_offsets(width, height, True)
    ys = axis_offsets(height, width, False)
    output = bytearray(width * height * bpp)
    for y in range(height):
        for x in range(width):
            source = (xs[x] | ys[y]) * bpp
            dest = (y * width + x) * bpp
            output[dest:dest + bpp] = data[source:source + bpp]
    return bytes(output)


def decode_texture(payload, entry, layout='Auto'):
    common, offset, _, fmt, size = entry['values']
    if (common >> 16) & 7 != 4:
        raise FormatError('Resource is not a texture.')
    if fmt & 4 or (fmt >> 4) & 15 != 2:
        raise FormatError('Only 2D textures are supported (no cube maps or volumes).')
    code = (fmt >> 8) & 255
    linear = code in LINEAR
    width = (size & 0xfff) + 1 if linear else 1 << ((fmt >> 20) & 15)
    height = ((size >> 12) & 0xfff) + 1 if linear else 1 << ((fmt >> 24) & 15)
    if width > 4096 or height > 4096:
        raise FormatError('Texture dimensions exceed 4096 pixels.')
    if not 0 <= offset < entry['end'] <= len(payload):
        raise FormatError('Invalid texture data offset.')
    data = payload[offset:entry['end']]
    info = dict(width=width, height=height, pixel_format=f'0x{code:02X}', warnings=[])
    if code in (0x0C, 0x0E, 0x0F):
        block = 8 if code == 0x0C else 16
        needed = ((width + 3) // 4) * ((height + 3) // 4) * block
        if len(data) < needed:
            raise FormatError('Truncated block-compressed texture.')
        fourcc = {0x0C: b'DXT1', 0x0E: b'DXT3', 0x0F: b'DXT5'}[code]
        fields = [124, 0x81007, height, width, needed, 0, 0] + [0] * 11
        fields += [32, 4, int.from_bytes(fourcc, 'little'), 0, 0, 0, 0, 0, 0x1000, 0, 0, 0, 0]
        with Image.open(io.BytesIO(b'DDS ' + struct.pack('<31I', *fields) + data[:needed])) as image:
            result = image.convert('RGBA')
        info['layout'] = fourcc.decode()
    else:
        base = LINEAR.get(code, code)
        if base not in BPP:
            raise FormatError(f'Unsupported pixel format 0x{code:02X}; no image was guessed.')
        bpp = BPP[base]
        row = width * bpp
        stride = row
        if linear:
            gpu_stride = (((size >> 24) & 255) + 1) * 64
            tight_size, padded_size = row * height, gpu_stride * height
            if layout == 'GPU pitch':
                stride = gpu_stride
            elif layout == 'Auto' and gpu_stride != row and padded_size <= len(data):
                # Compare exact size or conventional end-of-resource alignment.
                def fits(n):
                    return len(data) in {n, (n + 127) // 128 * 128, (n + 2047) // 2048 * 2048}
                if fits(padded_size) and not fits(tight_size):
                    stride = gpu_stride
                elif fits(tight_size) and not fits(padded_size):
                    stride = row
                else:
                    raise FormatError('Ambiguous row padding. Choose Tight rows or GPU pitch and retry.')
            if stride < row or stride * height > len(data):
                raise FormatError('Texture row layout exceeds the available data.')
            pixels = b''.join(data[y * stride:y * stride + row] for y in range(height))
            info['layout'] = 'tight rows' if stride == row else 'GPU pitch'
        else:
            if len(data) < row * height:
                raise FormatError('Truncated swizzled texture.')
            pixels = unswizzle(data[:row * height], width, height, bpp)
            info['layout'] = 'unswizzled'
        if base in (0x06, 0x07, 0x3A):
            rawmode = {0x06: 'BGRA', 0x07: 'BGRX', 0x3A: 'RGBA'}[base]
            mode = 'RGB' if base == 0x07 else 'RGBA'
            result = Image.frombytes(mode, (width, height), pixels, 'raw', rawmode).convert('RGBA')
        else:
            rgba = bytearray()
            for at in range(0, len(pixels), bpp):
                v = int.from_bytes(pixels[at:at+bpp], 'little')
                if base == 0x00:
                    color = (v, v, v, 255)
                elif base == 0x19:
                    color = (255, 255, 255, v)
                elif base == 0x1A:
                    color = (v & 255, v & 255, v & 255, v >> 8)
                elif base == 0x04:
                    color = (((v >> 8) & 15) * 17, ((v >> 4) & 15) * 17, (v & 15) * 17, (v >> 12) * 17)
                elif base == 0x05:
                    color = (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31, 255)
                else:
                    color = (((v >> 10) & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, (v & 31) * 255 // 31, 255 if base == 0x03 or v & 0x8000 else 0)
                rgba.extend(color)
            result = Image.frombytes('RGBA', (width, height), bytes(rgba))
    if (fmt >> 16) & 15 > 1:
        info['warnings'].append('Only the largest mip level was exported.')
    return result, info


def extract_file(source, destination, layout='Auto', cancelled=lambda: False):
    """One source into a NEW folder; errors in individual resources do not stop peers."""
    payload, entries, metadata = read_container(source)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    report = dict(source=str(Path(source).resolve()), **metadata, textures=[], exported=0, skipped=0, cancelled=False)
    for index, entry in enumerate(entries):
        if cancelled():
            report['cancelled'] = True
            break
        record = dict(name=entry['name'])
        try:
            image, details = decode_texture(payload, entry, layout)
            filename = f'{index + 1:04d}_{safe_name(entry["name"])}.png'
            image.save(destination / filename)
            record.update(status='exported', file=filename, **details)
            report['exported'] += 1
        except (ValueError, OSError, struct.error) as exc:
            record.update(status='skipped', reason=str(exc))
            report['skipped'] += 1
        report['textures'].append(record)
    (destination / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
