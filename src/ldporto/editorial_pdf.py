"""Small searchable editorial dossier writer. No renderer, inference or new dependency.

TrueType glyphs and a ToUnicode map preserve canonical Unicode text. The Windows
Arial font is read from the OS; callers on other systems can supply a local font.
"""
from pathlib import Path
import os
import re
import struct
import zlib


def _font_path():
    for path in (Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts/arial.ttf',
                 Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
                 Path('/Library/Fonts/Arial.ttf')):
        if path.is_file():
            return path
    raise ValueError('searchable_pdf_requires_local_truetype_font')


class _Font:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        u16 = lambda off: struct.unpack_from('>H', self.data, off)[0]
        self.tables = {}
        for i in range(u16(4)):
            pos = 12 + i*16
            name, _, offset, size = struct.unpack_from('>4sIII', self.data, pos)
            self.tables[name] = (offset, size)
        cmap = self.tables[b'cmap'][0]
        options = []
        for i in range(u16(cmap+2)):
            platform, encoding, offset = struct.unpack_from('>HHI', self.data, cmap+4+i*8)
            base = cmap+offset
            fmt = u16(base)
            if fmt in (4, 12) and platform in (0, 3):
                options.append((fmt, base))
        if not options:
            raise ValueError('unsupported_pdf_font_cmap')
        fmt, base = max(options)
        self.mapping = {}
        if fmt == 12:
            count = struct.unpack_from('>I', self.data, base+12)[0]
            for i in range(count):
                start, end, gid = struct.unpack_from('>III', self.data, base+16+i*12)
                self.mapping.update((cp, gid+cp-start) for cp in range(start, end+1))
        else:
            count = u16(base+6)//2
            ends, starts, deltas, offsets = base+14, base+16+count*2, base+16+count*4, base+16+count*6
            for i in range(count):
                delta, offset = u16(deltas+i*2), u16(offsets+i*2)
                for cp in range(u16(starts+i*2), u16(ends+i*2)+1):
                    if cp == 65535:
                        continue
                    gid = u16(offsets+i*2+offset+(cp-u16(starts+i*2))*2) if offset else cp
                    self.mapping[cp] = (gid+delta) % 65536 if gid else 0
        head, hhea, hmtx = (self.tables[n][0] for n in (b'head', b'hhea', b'hmtx'))
        self.units = u16(head+18)
        self.bbox = struct.unpack_from('>hhhh', self.data, head+36)
        self.ascent, self.descent = struct.unpack_from('>hh', self.data, hhea+4)
        self.widths = [u16(hmtx+i*4) for i in range(u16(hhea+34))]
        self.used = {}
        self.character_cids = {}

    def glyph(self, char):
        gid = self.mapping.get(ord(char), 0)
        if not gid and char not in '\r\n\t':
            # A visible code point label prevents silently dropping canonical text.
            raise ValueError('pdf_font_missing_character:U+%04X' % ord(char))
        return gid

    def width(self, text, size):
        return sum(self.widths[min(self.glyph(c), len(self.widths)-1)] for c in text)/self.units*size

    def encode(self, text):
        result = []
        for char in text:
            self.glyph(char)
            # Distinct Unicode codepoints can share one font glyph (Arial's
            # space/NBSP and hyphen/soft-hyphen are concrete examples). Give each
            # character its own CID so ToUnicode never overwrites either text.
            if char not in self.character_cids:
                cid = len(self.character_cids) + 1
                if cid > 65535:
                    raise ValueError('pdf_character_map_exceeds_cid_limit')
                self.character_cids[char] = cid
                self.used[cid] = char
            result.append('%04X' % self.character_cids[char])
        return ''.join(result)


def _pdf_string(text):
    return b'<FEFF'+str(text).encode('utf-16-be').hex().encode('ascii')+b'>'


def _jpeg_size(data):
    pos = 2
    while pos < len(data):
        if data[pos] != 255:
            raise ValueError('invalid_pdf_jpeg')
        marker = data[pos+1]
        pos += 2
        if marker in (0xD8, 0xD9):
            continue
        length = int.from_bytes(data[pos:pos+2], 'big')
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack_from('>HH', data, pos+3)
            channels = data[pos+7]
            if channels not in (1, 3):
                raise ValueError('unsupported_pdf_jpeg_colors')
            return width, height, channels
        pos += length
    raise ValueError('invalid_pdf_jpeg')


class EditorialPDF:
    """Paged sections, contents, source links, bookmarks and actual JPEG evidence."""
    def __init__(self, title, subtitle='', font_path=None):
        self.title = str(title)
        self.font = _Font(font_path or _font_path())
        self.pages = []
        self.sections = []
        self.images = []
        self._new_page()
        self.text(self.title, 20, '#133344')
        self.text(subtitle, 10)

    def _new_page(self):
        self.pages.append({'commands': [], 'links': [], 'images': []})
        self.y = 792

    def _space(self, height):
        if self.y-height < 55:
            self._new_page()

    def _line(self, text, size, color, url=None):
        self._space(size*1.45)
        rgb = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
        command = 'BT /F1 %s Tf %.3f %.3f %.3f rg 1 0 0 1 48 %.2f Tm <%s> Tj ET' % (
            size, *rgb, self.y, self.font.encode(text))
        page = self.pages[-1]
        page['commands'].append(command.encode('ascii'))
        if url and re.match(r'^https?://', str(url)):
            page['links'].append((48, self.y-3, min(548, 48+self.font.width(text,size)), self.y+size, str(url)))
        self.y -= size*1.45

    def text(self, text, size=10, color='#263B46', url=None):
        for paragraph in str(text or '').replace('\t','    ').splitlines() or ['']:
            # Wrap by measured glyph advances so long IDs/URLs cannot leave the page.
            line = ''
            for word in re.findall(r'\S+\s*', paragraph):
                if line and self.font.width(line+word.rstrip(), size)>495:
                    self._line(line.rstrip(), size, color, url)
                    line = ''
                for char in word:
                    if line and self.font.width(line+char, size)>495:
                        self._line(line.rstrip(), size, color, url)
                        line = ''
                    line += char
            self._line(line.rstrip(), size, color, url)

    def section(self, title):
        self._space(48)
        self.y -= 12
        self.sections.append((str(title), len(self.pages)-1))
        self.text(title, 14, '#006A75')

    def image(self, jpeg, caption=''):
        width, height, _ = _jpeg_size(jpeg)
        scale = min(495/width, 245/height)
        draw_w, draw_h = width*scale, height*scale
        self._space(draw_h+45)
        index = len(self.images)
        self.images.append(jpeg)
        self.y -= draw_h
        self.pages[-1]['images'].append(index)
        self.pages[-1]['commands'].append(('q %.2f 0 0 %.2f 48 %.2f cm /I%d Do Q' % (draw_w,draw_h,self.y,index)).encode())
        self.y -= 15
        self.text(caption, 9)

    def save(self, path):
        # Insert a readable index; the same entries are PDF outline destinations.
        original = self.pages
        offset = 1
        for _ in range(2):
            self.pages = []
            self._new_page()
            self.text('Índice de leitura', 18, '#006A75')
            for title, page in self.sections:
                self.text(title+'  ·  '+str(page+1+(offset if page else 0)), 10)
            contents = self.pages
            offset = len(contents)
        self.pages = original[:1]+contents+original[1:]
        offset = len(contents)
        page_number = lambda p: p if p == 0 else p+offset
        objects = []
        def add(data):
            objects.append(data if isinstance(data, bytes) else data.encode('ascii'))
            return len(objects)
        def stream(data, extra=b''):
            return b'<< /Length '+str(len(data)).encode()+b' '+extra+b' >>\nstream\n'+data+b'\nendstream'
        catalog, pages_ref, font_ref, outline_ref = add(b''), add(b''), add(b''), add(b'')
        page_refs = [add(b'') for _ in self.pages]
        for i,page in enumerate(self.pages):
            footer = 'L.D.PORTO · planejamento para revisão · %d/%d' % (i+1,len(self.pages))
            page['commands'].append(('BT /F1 8 Tf 0.3 0.3 0.3 rg 1 0 0 1 48 30 Tm <%s> Tj ET' % self.font.encode(footer)).encode())
        image_refs = []
        for jpeg in self.images:
            w,h,channels = _jpeg_size(jpeg)
            extra = ('/Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /%s /BitsPerComponent 8 /Filter /DCTDecode' % (w,h,'DeviceRGB' if channels==3 else 'DeviceGray')).encode()
            image_refs.append(add(stream(jpeg,extra)))
        font_file = add(stream(zlib.compress(self.font.data), b'/Filter /FlateDecode /Length1 '+str(len(self.font.data)).encode()))
        descriptor = add(('<< /Type /FontDescriptor /FontName /LDPortoEditorial /Flags 32 /FontBBox [%s] /ItalicAngle 0 /Ascent %d /Descent %d /CapHeight 720 /StemV 80 /FontFile2 %d 0 R >>' % (
            ' '.join(str(round(v/self.font.units*1000)) for v in self.font.bbox),round(self.font.ascent/self.font.units*1000),round(self.font.descent/self.font.units*1000),font_file)))
        widths = ' '.join('%d [%d]' % (char_id,round(self.font.widths[min(self.font.glyph(char),len(self.font.widths)-1)]/self.font.units*1000)) for char_id,char in sorted(self.font.used.items()))
        glyph_map = bytearray((max(self.font.used, default=0) + 1) * 2)
        for char_id, char in self.font.used.items():
            struct.pack_into('>H', glyph_map, char_id*2, self.font.glyph(char))
        glyph_map_ref = add(stream(zlib.compress(glyph_map), b'/Filter /FlateDecode'))
        cid = add('<< /Type /Font /Subtype /CIDFontType2 /BaseFont /LDPortoEditorial /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /FontDescriptor %d 0 R /CIDToGIDMap %d 0 R /W [%s] >>' % (descriptor,glyph_map_ref,widths))
        cmap = [' /CIDInit /ProcSet findresource begin 12 dict begin begincmap',
                '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def',
                '/CMapName /LDPortoUnicode def /CMapType 2 def',
                '1 begincodespacerange <0000> <FFFF> endcodespacerange']
        chars = sorted(self.font.used.items())
        for start in range(0,len(chars),100):
            chunk = chars[start:start+100]
            cmap.append('%d beginbfchar' % len(chunk))
            cmap.extend('<%04X> <%s>' % (gid,char.encode('utf-16-be').hex()) for gid,char in chunk)
            cmap.append('endbfchar')
        cmap.append('endcmap CMapName currentdict /CMap defineresource pop end end')
        unicode_ref = add(stream('\n'.join(cmap).encode('ascii')))
        objects[font_ref-1] = ('<< /Type /Font /Subtype /Type0 /BaseFont /LDPortoEditorial /Encoding /Identity-H /DescendantFonts [%d 0 R] /ToUnicode %d 0 R >>' % (cid,unicode_ref)).encode()
        for i,page in enumerate(self.pages):
            commands = add(stream(zlib.compress(b'\n'.join(page['commands'])),b'/Filter /FlateDecode'))
            annotations = []
            for x1,y1,x2,y2,url in page['links']:
                annotations.append(add(('<< /Type /Annot /Subtype /Link /Rect [%.2f %.2f %.2f %.2f] /Border [0 0 0] /A << /S /URI /URI ' % (x1,y1,x2,y2)).encode()+_pdf_string(url)+b' >> >>'))
            xobjects = ' '.join('/I%d %d 0 R' % (j,image_refs[j]) for j in page['images'])
            objects[page_refs[i]-1] = ('<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 %d 0 R >> /XObject << %s >> >> /Contents %d 0 R /Annots [%s] >>' % (pages_ref,font_ref,xobjects,commands,' '.join('%d 0 R' % a for a in annotations))).encode()
        outlines = [add(b'') for _ in self.sections]
        for i,(title,page) in enumerate(self.sections):
            siblings = (' /Prev %d 0 R' % outlines[i-1] if i else '')+(' /Next %d 0 R' % outlines[i+1] if i+1<len(outlines) else '')
            objects[outlines[i]-1] = b'<< /Title '+_pdf_string(title)+(' /Parent %d 0 R /Dest [%d 0 R /Fit]%s >>' % (outline_ref,page_refs[page_number(page)],siblings)).encode()
        objects[outline_ref-1] = ('<< /Type /Outlines /Count %d%s >>' % (len(outlines),(' /First %d 0 R /Last %d 0 R' % (outlines[0],outlines[-1])) if outlines else '')).encode()
        objects[pages_ref-1] = ('<< /Type /Pages /Count %d /Kids [%s] >>' % (len(page_refs),' '.join('%d 0 R' % p for p in page_refs))).encode()
        objects[catalog-1] = ('<< /Type /Catalog /Pages %d 0 R /Outlines %d 0 R /PageMode /UseOutlines >>' % (pages_ref,outline_ref)).encode()
        output = bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n'); offsets = [0]
        for i,obj in enumerate(objects,1):
            offsets.append(len(output)); output.extend(('%d 0 obj\n' % i).encode()+obj+b'\nendobj\n')
        xref = len(output)
        output.extend(('xref\n0 %d\n0000000000 65535 f \n' % (len(objects)+1)).encode())
        output.extend(b''.join(('%010d 00000 n \n' % n).encode() for n in offsets[1:]))
        output.extend(('trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objects)+1,catalog,xref)).encode())
        Path(path).write_bytes(output)
        return {'pages': len(self.pages), 'searchable': True, 'unicode_font_embedded': True}
