from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'test-runtime'))
from lupa import LuaRuntime

lua = LuaRuntime(unpack_returned_tuples=True)
lua.globals().package.path = (ROOT / 'src/?.lua').as_posix() + ';' + (ROOT / 'vendor/?.lua').as_posix() + ';' + lua.globals().package.path
with tempfile.TemporaryDirectory() as directory:
    (Path(directory) / 'BindingProfiles').mkdir()
    lua.globals().test_root = Path(directory).as_posix() + '/'
    lua.execute('''
    local function object(full) return {IsValid=function() return true end,GetFullName=function() return full end} end
    FName=function(s) return s end
    local texture=object('Texture2D /Game/Aircraft/PP0021_su57/T_Body.T_Body')
    local material=object('MaterialInstanceConstant /Game/Aircraft/PP0021_su57/M_Body.M_Body')
    local inherited=object('MaterialInstanceConstant /Game/Aircraft/PP0021_su57/M_Parent.M_Parent')
    inherited.TextureParameterValues={ForEach=function(_,callback)
       callback(0,{get=function() return {ParameterInfo={Name={ToString=function() return 'BaseColor' end}},ParameterValue=texture} end})
    end}
    material.Parent=inherited;material.K2_GetTextureParameterValue=function() return texture end
    local writes=0;local body=object('SkeletalMeshComponent Body')
    body.GetNumMaterials=function() return 2 end;body.GetMaterial=function() return material end
    body.GetSkeletalMeshAsset=function() return object('SkeletalMesh /Game/Aircraft/PP0021_su57/SK_Body.SK_Body') end
    body.SetMaterial=function() writes=writes+1 end
    local ctx={component=body,phase='preparation',offline_verified=true,aircraft_id='PP0021_su57',fingerprint='body'}
    local adapter={applied={},context=function() return ctx end}
    local capture=require('binding_capture').new(test_root,adapter,require('json'))
    local result=capture:save('PP0021_su57')
    assert(#result.materials==2 and result.materials[1].slot==0 and result.materials[2].slot==1)
    assert(result.materials[1].parameters[1].parameter=='BaseColor' and writes==0)
    assert(not pcall(function() capture:profile('PP0022_f16c') end))
    adapter.applied.body={};assert(not pcall(function() capture:profile() end));adapter.applied.body=nil
    ctx.phase='mission';assert(not pcall(function() capture:profile() end));ctx.phase='preparation'
    ctx.offline_verified=false;assert(not pcall(function() capture:profile() end));ctx.offline_verified=true
    ctx.model_ready=false;assert(not pcall(function() capture:profile() end));ctx.model_ready=true
    local request=assert(io.open(test_root..'binding-request.json','wb'))
    request:write(require('json').encode({schema_version=1,aircraft_id='PP0021_su57',token=string.rep('a',32)}));request:close()
    assert(capture:poll());assert(not capture:poll());assert(writes==0)
    ''')
    profile = json.loads((Path(directory) / 'BindingProfiles/PP0021_su57.json').read_text())
    reply = json.loads((Path(directory) / 'binding-response.json').read_text())
    assert reply['ok'] and reply['profile'] == profile and not (Path(directory) / 'binding-request.json').exists()
print('Binding capture: inheritance, grouping inputs, read-only writes, STD/offline/page/model guards, request reply passed.')
