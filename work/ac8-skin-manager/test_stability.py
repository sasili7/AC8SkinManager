"""Regression checks for issues demonstrated by the 2026-10-09 audit."""
from pathlib import Path
import ast
import json
import shutil
import sys
import tempfile

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT / 'test-runtime'))
from lupa import LuaRuntime

vm = LuaRuntime(unpack_returned_tuples=True)
vm.globals().package.path = (PROJECT / 'src/?.lua').as_posix() + ';' + (PROJECT / 'vendor/?.lua').as_posix() + ';' + vm.globals().package.path
for node in ast.parse((PROJECT / 'test_framework.py').read_text(encoding='utf-8')).body:
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        call = node.value
        if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == 'lua' and call.func.attr == 'execute':
            source = ast.literal_eval(call.args[0])
            if any(marker in source for marker in ('function manifest(', 'function object(', 'function ui_fixture(', 'function context_fixture(')):
                vm.execute(source)

checks = {}


def check(name, source):
    vm.execute(source)
    checks[name] = True


check('deleted_or_cross_aircraft_selection_is_pruned', '''
local c=Core.new({schema_version=1,skins={}}, {selections={PP0021_su57='deleted'}}, function() end)
assert(next(c.saved.selections)==nil)
local c=state();c.saved.selections.PP0021_su57=c.catalog.skins[2].id
local repaired=Core.new(c.catalog,c.saved,function() end)
assert(repaired.saved.selections.PP0021_su57==nil)
assert(Core.new({schema_version=1,skins={}}, 123).saved.selections)
assert(Core.new({schema_version=1,skins={}}, {selections=123}).saved.selections)
''')
check('failed_or_deleted_skin_never_disables_native_skin_menu', '''
local c=state();local list=object('native-list');list.enabled=true
function list:GetIsEnabled() return self.enabled end
function list:SetIsEnabled(v) self.enabled=v end
local a={last_aircraft_id='PP0021_su57',native_skin_page=function() return {WBP_Menu_SkinEmblem_ListView_000=list} end}
local applied=false;function a:has_applied() return applied end
local skin=c.catalog.skins[1];c.saved.selections.PP0021_su57=skin.id
local mode=require('native_mode').new()
mode:sync(a,c,true);assert(list.enabled)
applied=true;mode:sync(a,c,true);assert(not list.enabled)
c.catalog.skins={};mode:sync(a,c,true);assert(list.enabled)
''')
check('partial_registration_keeps_successful_skins_available', '''
local a=fixture();a.config.package_registration_enabled=true;a.root='test/'
local open,getenv,remove=io.open,os.getenv,os.remove
os.getenv=function() return '1' end;os.remove=function() return true end
local calls=0;a.native_register=function() calls=calls+1 end
io.open=function() return {read=function() return '{"revision":"20261008-cached-store","state":"partial","registered":1,"failed":1}' end,close=function() end} end
assert(a:register_independent_packages());assert(a:register_independent_packages());assert(calls==1)
io.open,os.getenv,os.remove=open,getenv,remove
''')
check('fully_blocked_registration_is_not_retried_forever', '''
local a=fixture();a.config.package_registration_enabled=true;a.root='test/'
local open,getenv,remove=io.open,os.getenv,os.remove
os.getenv=function() return '1' end;os.remove=function() return true end
local calls=0;a.native_register=function() calls=calls+1 end
io.open=function() return {read=function() return '{"revision":"20261008-cached-store","state":"blocked","registered":0}' end,close=function() end} end
for _=1,10 do assert(not a:register_independent_packages()) end;assert(calls==1)
io.open,os.getenv,os.remove=open,getenv,remove
''')
check('same_page_resolution_change_rebuilds_button_layout', '''
fixture();local c,a=state();c:set_aircraft(a.current);local ctx,root=ui_fixture()
root.GetCachedGeometry=function() return {} end
local width=1920;local library={GetLocalSize=function() return {X=width,Y=1080} end}
local find=StaticFindObject
StaticFindObject=function(p) if p=='/Script/UMG.Default__SlateBlueprintLibrary' then return library end;return find(p) end
FindAllOf=function() return {} end
local menu=require('menu').new();assert(menu:render(c,ctx));local before=menu.layout.button_width
local old=menu.panel;old.GetParent=function() return root end
width=3840;assert(menu:render(c,ctx));assert(menu.layout.button_width>before and old.removed)
''')
check('collected_native_mid_is_rebuilt_without_retaining_mod_texture', '''
local a,ctx,skin,body,original=fixture();assert(a:apply(ctx,skin))
original.IsValid=function() return false end
assert(a:apply(ctx,{id='original',aircraft_id=ctx.aircraft_id}))
assert(body.materials[0]:K2_GetTextureParameterValue('BodyColor'):GetFullName()=='original-texture')
assert(a:is_applied(ctx,{id='original'}))
''')
check('failed_native_texture_reconstruction_leaves_previous_skin_intact', '''
local a,ctx,skin,body,original=fixture();assert(a:apply(ctx,skin))
local managed=body.materials[0];original.IsValid=function() return false end
local find=StaticFindObject;StaticFindObject=function(p) if p=='original-texture' then return nil end;return find(p) end
assert(not a:apply(ctx,{id='original',aircraft_id=ctx.aircraft_id}))
assert(body.materials[0]==managed and a:is_applied(ctx,skin))
''')
check('std_accepts_new_native_texture_on_the_original_mid', '''
local a,ctx,skin,body,original=fixture();assert(a:apply(ctx,skin))
local newer=object('native-skin-two');original.params.BodyColor=newer
assert(a:apply(ctx,{id='original',aircraft_id=ctx.aircraft_id}))
assert(body.materials[0]==original and body.materials[0].params.BodyColor==newer)
assert(not a:owns_overrides(ctx.aircraft_id,skin.id))
''')
check('std_preserves_native_controller_mid_identity_after_in_place_refresh', '''
local a,ctx,skin,body,original=fixture();assert(a:apply(ctx,skin))
local newer=object('native-skin-two');body.materials[0].params.BodyColor=newer
assert(a:apply(ctx,{id='original',aircraft_id=ctx.aircraft_id}))
assert(body.materials[0]==original and original.params.BodyColor==newer)
-- The native controller still writes its original object after STD.
local third=object('native-skin-three');original.params.BodyColor=third
assert(body.materials[0].params.BodyColor==third and a:is_applied(ctx,{id='original'}))
''')
check('mod_reapply_retains_latest_native_baseline_for_std', '''
local a,ctx,skin,body,original=fixture();assert(a:apply(ctx,skin))
local newer=object('native-skin-two');body.materials[0].params.BodyColor=newer
assert(a:apply(ctx,skin));assert(a:is_applied(ctx,skin))
assert(a:apply(ctx,{id='original',aircraft_id=ctx.aircraft_id}))
assert(body.materials[0]==original and original.params.BodyColor==newer)
''')
check('std_native_parameter_updates_roll_back_with_failed_persistence', '''
local a,ctx,skin,body,original=fixture();assert(a:apply(ctx,skin))
local managed=body.materials[0];local old=original.params.BodyColor
managed.params.BodyColor=object('native-skin-two')
local ok,_,undo=a:apply(ctx,{id='original',aircraft_id=ctx.aircraft_id});assert(ok)
undo();assert(body.materials[0]==managed and original.params.BodyColor==old)
assert(a:owns_overrides(ctx.aircraft_id,skin.id))
''')
check('missing_original_record_does_not_report_success_or_release_authority', '''
local a,ctx,skin,body=fixture();assert(a:apply(ctx,skin));local managed=body.materials[0]
a.originals[ctx.fingerprint]={}
assert(not a:apply(ctx,{id='original',aircraft_id=ctx.aircraft_id}))
assert(body.materials[0]==managed and a:owns_overrides(ctx.aircraft_id,skin.id))
''')
check('native_list_stays_locked_during_mod_refresh_then_std_releases_it', '''
local a,ctx,skin,body=fixture();assert(a:apply(ctx,skin));a.last_aircraft_id=ctx.aircraft_id
local list=object('native-list');list.enabled=true;list.writes=0
function list:GetIsEnabled() return self.enabled end
function list:SetIsEnabled(v) self.enabled=v;self.writes=self.writes+1 end
function a:native_skin_page() return {WBP_Menu_SkinEmblem_ListView_000=list} end
local core={catalog={skins={skin}},saved={selections={[ctx.aircraft_id]=skin.id}}}
body.materials[0].params.BodyColor=object('native-skin-two')
assert(not a:has_applied(ctx.aircraft_id,skin.id) and a:owns_overrides(ctx.aircraft_id,skin.id))
local mode=require('native_mode').new();mode:sync(a,core,true);assert(not list.enabled)
mode:sync(a,core,true);assert(list.writes==1)
assert(a:apply(ctx,{id='original',aircraft_id=ctx.aircraft_id}))
core.saved.selections[ctx.aircraft_id]='original';mode:sync(a,core,true)
assert(list.enabled and next(mode.locked)==nil)
local writes=body.writes
for _=1,20 do mode:sync(a,core,true);assert(a:is_applied(ctx,{id='original'})) end
assert(body.writes==writes and list.writes==2)
''')
check('native_animation_gate_is_not_mistaken_for_a_manager_owned_lock', '''
local c=state();local list=object('native-list');list.enabled=false
function list:GetIsEnabled() return self.enabled end
function list:SetIsEnabled(v) self.enabled=v end
local a={last_aircraft_id='PP0021_su57',owns_overrides=function() return true end,
native_skin_page=function() return {WBP_Menu_SkinEmblem_ListView_000=list} end}
c.saved.selections.PP0021_su57=c.catalog.skins[1].id
local mode=require('native_mode').new();mode:sync(a,c,true);assert(next(mode.locked)==nil)
list.enabled=true;mode:sync(a,c,true);assert(not list.enabled)
c.saved.selections.PP0021_su57='original';mode:sync(a,c,true);assert(list.enabled)
''')
check('destroyed_actor_state_is_pruned_in_repeated_switches', '''
local a,ctx,skin,body=fixture();local alive=true
body.IsValid=function() return alive end
for i=1,100 do
    alive=true;ctx.fingerprint='actor-'..i;assert(a:apply(ctx,skin))
    alive=false;a:prune()
end
assert(next(a.applied)==nil and next(a.originals)==nil and next(a.components)==nil and next(a.textures)==nil)
''')
check('object_enumeration_is_cached_and_invalidated_for_new_widgets', '''
local a,w,comps,add=context_fixture();add('PP0021_su57',false,true)
local scan=FindAllOf;local calls=0;FindAllOf=function(c) calls=calls+1;return scan(c) end
local clock=os.time;os.time=function() return 100 end
assert(a:context());local initial=calls
for _=1,20 do assert(a:context()) end;assert(calls==initial)
a.discovery_dirty=true;assert(a:context());assert(calls>initial)
os.time=clock
''')
check('mission_context_rejects_npcs_and_requires_offline_local_player', '''
local a,ctx,skin,body=fixture()
local pawn=object('LivePlayerPlane /Game/Maps/Mission.Test.Player')
local local_player=true
pawn.IsPlayerControlled=function() return local_player end
pawn.IsLocallyControlled=function() return local_player end
pawn.GetComponentsByClass=function() return {body} end
body.GetFullName=function() return 'SkeletalMeshComponent /Game/Maps/Mission.Test.Player.PlaneBodyMesh' end
body.GetOwner=function() return pawn end
body.GetSkeletalMeshAsset=function() return object('SkeletalMesh /Game/Vehicles/Aircraft/PP/PP0021_su57/SK_Body') end
FindAllOf=function(c) return c=='LivePlayerPlane' and {pawn} or {} end
local getenv=os.getenv;os.getenv=function() return '1' end
local mission=assert(a:mission_context());assert(mission.phase=='mission' and mission.aircraft_id==skin.aircraft_id)
assert(a:apply(mission,skin));assert(a:is_applied(mission,skin))
local_player=false;assert(a:mission_context()==nil)
os.getenv=function() return nil end;assert(a:mission_context()==nil)
os.getenv=getenv
''')

with tempfile.TemporaryDirectory(prefix='ac8-stability-') as temporary:
    temp = Path(temporary)
    good_manifest = temp / 'good-skin.json'
    empty_manifest = temp / 'empty-skin.json'
    good_manifest.write_text(vm.execute('return require("json").encode(manifest())'), encoding='utf-8')
    empty_manifest.write_bytes(b'')
    files = vm.table_from([
        vm.table_from({'__name': 'skin.json', '__absolute_path': empty_manifest.as_posix()}),
        vm.table_from({'__name': 'skin.json', '__absolute_path': good_manifest.as_posix()}),
    ])
    tree = vm.table_from({'__files': files})
    result = vm.execute('return require("registry").discover(..., require("json"))', tree)
    assert len(result) == 1 and result[1]['local_id'] == 'blue'
    checks['empty_manifest_does_not_hide_other_valid_skins'] = True
    path = temp / 'selections.json'
    path.write_text('{broken', encoding='utf-8')
    path.with_suffix('.json.bak').write_text('{"selections":{"PP0021_su57":"original"}}', encoding='utf-8')
    result = vm.execute('local s=require("storage");return s.read(...,{selections={}},s.selections,require("json"))', path.as_posix())
    assert result['selections']['PP0021_su57'] == 'original'
    vm.execute('require("storage").write(...,{selections={PP0021_su57="original"}},require("json"))', path.as_posix())
    assert json.loads(path.read_text())['selections']['PP0021_su57'] == 'original'
    assert json.loads(path.with_suffix('.json.bak').read_text())['selections']['PP0021_su57'] == 'original'
    assert list(temp.glob('selections.json.invalid-*'))
    checks['corrupt_primary_recovers_backup_and_preserves_damaged_file'] = True
    path.write_text('123', encoding='utf-8'); path.with_suffix('.json.bak').unlink()
    result = vm.execute('local s=require("storage");return s.read(...,{selections={}},s.selections,require("json"))', path.as_posix())
    assert list(result['selections'].items()) == []
    checks['invalid_json_types_use_defaults'] = True

    isolated = temp / 'AC8SkinManager'
    shutil.copytree(PROJECT / 'src', isolated / 'Scripts')
    shutil.copy2(PROJECT / 'vendor/json.lua', isolated / 'Scripts/json.lua')
    (isolated / 'catalog.json').write_text('{"schema_version":1,"aircraft":[],"skins":[]}', encoding='utf-8')
    runtime = LuaRuntime(unpack_returned_tuples=True)
    runtime.execute('''
    scans=0;loops={};callbacks={}
    IterateGameDirectories=function() return {Game={Binaries={Win64={ue4ss={Mods={AC8SkinManager={Skins={}}}}}}}} end
    FindAllOf=function() scans=scans+1;return {} end
    ExecuteInGameThread=function(fn) fn() end
    LoopAsync=function(ms,fn) loops[ms]=fn end
    Key={F6=117,F7=118,F9=120,F10=121,F11=122}
    IsKeyBindRegistered=function(k) return callbacks[k]~=nil end
    RegisterKeyBind=function(k,fn) callbacks[k]=fn end
    print=function() end
    ''')
    runtime.execute('dofile(...)', (isolated / 'Scripts/main.lua').as_posix())
    runtime.execute('for i=1,300 do loops[33]() end;for i=1,8 do loops[1200]() end')
    assert runtime.globals().scans == 0
    checks['empty_library_performs_zero_object_scans'] = True

report = {'revision': '20261009-native-coexistence', 'checks': checks,
          'scope': 'Isolated regression tests; actual game frame times and mission rendering require in-game verification.'}
(PROJECT / 'stability-test-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
