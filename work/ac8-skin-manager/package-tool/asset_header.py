"""Narrow UE5.4 cooked Texture2D relocation; texture payloads stay byte-identical."""
import struct
import zlib


class UnsupportedAsset(ValueError):
    pass


def name_hash(text):
    # Unreal's two 16-bit name hashes: Strihash_DEPRECATED and StrCrc32.
    table = []
    for i in range(256):
        value = i << 24
        for _ in range(8):
            value = ((value << 1) ^ (0x04C11DB7 if value & 0x80000000 else 0)) & 0xffffffff
        table.append(value)
    old = 0
    for b in text.upper().encode('ascii'):
        old = ((old >> 8) ^ table[(old ^ b) & 255]) & 0xffffffff
    current = zlib.crc32(b''.join(struct.pack('<I', ord(c)) for c in text))
    return struct.pack('<I', (old & 65535) | ((current & 65535) << 16))


class Header:
    def __init__(self, data):
        self.data, self.pos, self.fields = data, 0, {}
        def integer(key, width=4):
            self.fields[key] = (self.pos, width)
            value = self.read('<q' if width == 8 else '<i')
            setattr(self, key, value)
            return value
        def zero(key):
            if integer(key) != 0:
                raise UnsupportedAsset('不支持带有 ' + key + ' 的资源。')
        if self.read('<I') != 0x9e2a83c1 or self.read('<i') != -8:
            raise UnsupportedAsset('需要 UE5 cooked 贴图资源。')
        # retoc UE5.4 legacy output is unversioned and has no custom versions.
        if any(self.read('<i') != 0 for _ in range(5)):
            raise UnsupportedAsset('资源版本布局不在当前转换器支持范围内。')
        integer('header_size')
        self.package_span = (self.pos, None)
        self.package = self.string()
        self.package_span = (self.package_span[0], self.pos)
        flags = self.read('<I')
        if not flags & 0x80000000:
            raise UnsupportedAsset('不支持未烘焙的编辑器资源。')
        integer('name_count'); integer('name_offset')
        zero('soft_object_count'); integer('soft_object_offset')
        zero('gather_count'); zero('gather_offset')
        integer('export_count'); integer('export_offset')
        integer('import_count'); integer('import_offset'); integer('depends_offset')
        for key in ('soft_package_count', 'soft_package_offset', 'searchable_offset', 'thumbnail_offset'):
            zero(key)
        self.pos += 16  # GUID
        generations = self.read('<i')
        if not 1 <= generations < 10:
            raise UnsupportedAsset('无效的资源 generation 表。')
        self.pos += generations * 8
        self.pos += 28  # Two empty engine versions emitted by retoc
        if self.data[self.pos - 28:self.pos] != bytes(28):
            raise UnsupportedAsset('不支持带有非空 engine version 的 cooked header。')
        zero('compression_flags'); zero('compressed_chunks')
        self.pos += 4  # PackageSource
        zero('additional_packages')
        integer('registry_offset'); integer('bulk_offset', 8)
        zero('world_tile_offset'); zero('chunk_ids')
        integer('preload_count'); integer('preload_offset')
        integer('referenced_names'); integer('payload_toc', 8); integer('resource_offset')
        if self.pos != self.name_offset or self.header_size != len(data):
            raise UnsupportedAsset('资源 header 布局不匹配；未进行修改。')
        if not 0 < self.name_count < 4096 or self.export_count != 1 or not 0 < self.import_count < 32:
            raise UnsupportedAsset('仅支持单个 Texture2D 导出的贴图资源。')
        self.names = []
        for _ in range(self.name_count):
            start = self.pos
            name = self.string()
            self.pos += 4
            self.names.append((start, self.pos, name))
        if self.pos != self.import_offset:
            raise UnsupportedAsset('贴图名称表与导入表不连续。')
        self.import_names = []
        for i in range(self.import_count):
            at = self.import_offset + i * 32
            name_id = struct.unpack_from('<i', data, at + 20)[0]
            self.import_names.append(self.names[name_id][2])
        if self.import_offset + self.import_count * 32 != self.export_offset:
            raise UnsupportedAsset('不支持该导入表格式。')
        class_id, _, _, _, export_name = struct.unpack_from('<5i', data, self.export_offset)
        if class_id >= 0 or self.import_names[-class_id - 1] != 'Texture2D':
            raise UnsupportedAsset('包内包含非 Texture2D 资源。')
        if any(n.startswith('/Game/') and n != self.package for _, _, n in self.names):
            raise UnsupportedAsset('贴图包含其它游戏资源引用，需作者先拆分依赖。')
        self.export_name = self.names[export_name][2]
        self.serial_offset = struct.unpack_from('<q', data, self.export_offset + 36)[0]
        if self.serial_offset != self.header_size:
            raise UnsupportedAsset('不支持该导出数据偏移布局。')

    def read(self, fmt):
        try:
            value = struct.unpack_from(fmt, self.data, self.pos)[0]
        except struct.error as exc:
            raise UnsupportedAsset('贴图 header 不完整。') from exc
        self.pos += struct.calcsize(fmt)
        return value

    def string(self):
        count = self.read('<i')
        if not 0 < count < 65536 or self.pos + count > len(self.data):
            raise UnsupportedAsset('仅支持有效的 ASCII cooked 名称。')
        raw = self.data[self.pos:self.pos + count]
        self.pos += count
        if not raw.endswith(b'\0'):
            raise UnsupportedAsset('无效字符串。')
        return raw[:-1].decode('ascii')

    def relocate(self, new_package):
        def string(value):
            raw = value.encode('ascii') + b'\0'
            return struct.pack('<i', len(raw)) + raw
        edits = [(self.package_span[0], self.package_span[1], string(new_package))]
        for start, end, value in self.names:
            if value == self.package:
                edits.append((start, end, string(new_package) + name_hash(new_package)))
        if len(edits) != 2:
            raise UnsupportedAsset('包名称不是预期的两个引用。')
        def mapped(offset):
            return offset + sum(len(replacement) - (end - start) for start, end, replacement in edits if end <= offset)
        patched = bytearray(self.data)
        for start, end, replacement in sorted(edits, reverse=True):
            patched[start:end] = replacement
        delta = len(patched) - len(self.data)
        for key in ('header_size', 'name_offset', 'soft_object_offset', 'export_offset', 'import_offset',
                    'depends_offset', 'registry_offset', 'bulk_offset', 'preload_offset', 'payload_toc', 'resource_offset'):
            at, width = self.fields[key]
            value = getattr(self, key)
            if value > 0:
                struct.pack_into('<q' if width == 8 else '<i', patched, mapped(at), mapped(value))
        struct.pack_into('<q', patched, mapped(self.export_offset + 36), self.serial_offset + delta)
        if self.resource_offset > 0:
            at = mapped(self.resource_offset)
            version, count = struct.unpack_from('<2i', patched, at)
            if version != 1 or not 0 <= count <= 4096 or at + 8 + count * 44 != len(patched):
                raise UnsupportedAsset('不支持该 bulk resource 表。')
            for i in range(count):
                entry = at + 8 + i * 44
                flags = struct.unpack_from('<I', patched, entry + 40)[0]
                if flags & 0x40:  # Inline export payload offsets include header.
                    for field in (4, 12):
                        value = struct.unpack_from('<q', patched, entry + field)[0]
                        if value >= self.header_size:
                            struct.pack_into('<q', patched, entry + field, value + delta)
                elif not flags & 0x10000:
                    raise UnsupportedAsset('不支持需要 bulk offset fixup 的贴图。')
        check = Header(bytes(patched))
        if check.package != new_package or check.export_name != self.export_name:
            raise UnsupportedAsset('独立资源名称回读失败。')
        return bytes(patched)
