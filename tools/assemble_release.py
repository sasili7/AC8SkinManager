"""Reproduce the checked release ZIP exactly, then verify its content against source."""
from pathlib import Path
import base64
import hashlib
import io
import json
import zipfile

ROOT = Path(__file__).resolve().parent.parent

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    spec = json.loads((ROOT / "tools/release-delta.json").read_text(encoding="utf-8"))
    def safe(relative):
        path = (ROOT / relative).resolve()
        path.relative_to(ROOT)
        return path
    base = safe(spec["base_path"]).read_bytes()
    assert sha(base) == spec["base_sha256"], "Release base checksum mismatch"
    parts = []
    for op in spec["operations"]:
        if "data" in op:
            parts.append(base64.b64decode(op["data"], validate=True))
        else:
            offset, size = op["offset"], op["size"]
            assert isinstance(offset, int) and isinstance(size, int)
            assert 0 <= offset <= len(base) and 0 <= size <= len(base) - offset
            parts.append(base[offset:offset + size])
    data = b"".join(parts)
    assert len(data) == spec["target_bytes"]
    assert sha(data) == spec["target_sha256"], "Reconstructed archive checksum mismatch"
    inventory = json.loads((ROOT / "docs/release-files.json").read_text(encoding="utf-8"))
    assert inventory["sha256"] == sha(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        expected = {row["path"]: row for row in inventory["files"]}
        assert len(expected) == len(archive.infolist())
        assert set(expected) == set(archive.namelist())
        for name, row in expected.items():
            content = archive.read(name)
            assert len(content) == row["size"] and sha(content) == row["sha256"], name
            relative = Path(name).relative_to("AC8SkinManager")
            source = safe(str(Path("distribution") / relative))
            if source.is_file():
                assert source.read_bytes() == content, str(source)
            if relative.suffix == ".lua" and relative.parent.name == "Scripts":
                source = safe(str(Path("work/ac8-skin-manager/src") / relative.name))
                if relative.name == "json.lua":
                    source = safe("work/ac8-skin-manager/vendor/json.lua")
                assert source.read_bytes() == content, str(source)
        compatibility = json.loads(archive.read("AC8SkinManager/compatibility.json"))
        assert set(row["path"] for row in compatibility["files"]) == {
            Path(name).relative_to("AC8SkinManager").as_posix()
            for name in archive.namelist() if name != "AC8SkinManager/compatibility.json"}
        for row in compatibility["files"]:
            assert sha(archive.read("AC8SkinManager/" + row["path"])) == row["sha256"], row["path"]
    target = safe(spec["target_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".zip.tmp")
    temporary.write_bytes(data)
    temporary.replace(target)
    print(json.dumps({"archive": str(target.relative_to(ROOT)), "sha256": sha(data),
                      "bytes": len(data), "files": len(expected), "source_verified": True}, indent=2))

if __name__ == "__main__":
    main()
