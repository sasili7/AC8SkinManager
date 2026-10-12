"""Mission handoff regressions, using real Lua modules and isolated engine objects."""
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
            if any(marker in source for marker in ('function manifest(', 'function object(')):
                vm.execute(source)


class RemoteItem:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class RemoteArray:
    def __init__(self, *items):
        self.items = items

    def ForEach(self, callback):
        for index, value in enumerate(self.items):
            callback(index, RemoteItem(value))


vm.globals().remote_array = RemoteArray
vm.execute('''
function mission_fixture(serial)
    local a,hangar,skin,body,original=fixture()
    serial=serial or '1'
    local plane=object('BP_PlayerPlane_PP0021_su57_C /Game/Maps/Ingame/Mission001.Mission001:PersistentLevel.Player_'..serial)
    body.GetFullName=function() return 'SkeletalMeshComponent /Game/Maps/Ingame/Mission001.Mission001:PersistentLevel.Player_'..serial..'.PlaneBodyMesh' end
    body.GetOwner=function() return plane end
    body.GetSkeletalMeshAsset=function() return object('SkeletalMesh /Game/Vehicles/Aircraft/PP/PP0021_su57/Model/SK_PP0021_su57.SK_PP0021_su57') end
    plane.PlaneBodyMesh=body
    plane.GetComponentsByClass=function() return {body} end
    FindAllOf=function(c) return c=='LivePlayerPlane' and {plane} or {} end
    os.getenv=function() return '1' end
    return a,plane,body,skin,original,hangar
end
''')
checks = {}


def check(name, source):
    vm.execute(source)
    checks[name] = True


check('custom_player_actor_without_pawn_methods_is_detected_and_skinned', '''
local a,p,b,s=mission_fixture()
assert(p.IsPlayerControlled==nil and p.IsLocallyControlled==nil)
local c=assert(a:mission_context());assert(c.phase=='mission' and c.aircraft_id==s.aircraft_id)
assert(a:apply(c,s));assert(a:is_applied(c,s));assert(a.mission_discovery.state=='ready')
''')
check('direct_body_property_accepts_generated_component_names', '''
local a,p,b,s=mission_fixture()
b.GetFullName=function() return 'SkeletalMeshComponent /Game/Maps/Ingame/Mission001.Player.SkeletalMeshB67E700A4DA57390A0EC4096810B7249' end
b.GetSkeletalMeshAsset=function() error('method unavailable') end
b.SkeletalMesh=object('SkeletalMesh /Game/Vehicles/Aircraft/PP/PP0021_su57/Model/Body.Body')
assert(a:mission_context().component==b)
''')
check('reflected_component_array_fallback_is_supported', '''
local a,p,b=mission_fixture();p.PlaneBodyMesh=nil
p.GetComponentsByClass=function() return remote_array(b,b) end
local c=assert(a:mission_context());assert(c.component==b and a.mission_discovery.bodies==1)
''')
check('explicit_nonlocal_or_ai_actor_is_never_written', '''
for _,flag in ipairs({'IsPlayerControlled','IsLocallyControlled'}) do
    local a,p,b=mission_fixture();p[flag]=function() return false end
    assert(a:mission_context()==nil and b.writes==0 and a.mission_discovery.rejected==1)
end
''')
check('multiple_player_instances_and_unowned_bodies_are_rejected', '''
local a,p,b=mission_fixture();local other=object('LivePlayerPlane /Game/Maps/Ingame/Other.Player')
FindAllOf=function(c) return c=='LivePlayerPlane' and {p,other} or {} end
assert(a:mission_context()==nil and a.mission_discovery.state=='ambiguous-player' and b.writes==0)
a,p,b=mission_fixture();b.GetOwner=function() return other end
assert(a:mission_context()==nil and a.mission_discovery.state=='waiting-body')
''')
check('hangar_and_offline_and_disabled_mission_guards_are_preserved', '''
local a,p,b=mission_fixture()
os.getenv=function() return nil end;assert(a:mission_context()==nil and b.writes==0)
os.getenv=function() return '1' end;a.config.mission_switch_enabled=false;assert(a:mission_context()==nil)
a.config.mission_switch_enabled=true
p.GetFullName=function() return 'LivePlayerPlane /Game/Maps/Hangar/PL_Hangar005.Player' end
assert(a:mission_context()==nil and b.writes==0)
''')
check('mission_choice_is_restored_without_a_visible_menu_or_current_core_aircraft', '''
local a,p,b,s=mission_fixture()
local core=Core.new({schema_version=1,skins={s}}, {selections={[s.aircraft_id]=s.id}})
assert(core.aircraft==nil)
local r=require('reconcile').new();local c=assert(a:mission_context())
assert(r:update(a,core,a.config,c,nil,100));assert(a:is_applied(c,s))
local writes=b.writes
for i=1,100 do assert(r:update(a,core,a.config,c,nil,100+i)) end
assert(b.writes==writes and core.aircraft==nil)
''')
check('four_streaming_failures_recover_with_bounded_backoff', '''
local a,p,b,s=mission_fixture();local c=assert(a:mission_context())
local core=Core.new({schema_version=1,skins={s}}, {selections={[s.aircraft_id]=s.id}})
local real=a.apply;local calls=0
a.apply=function(self,ctx,skin) calls=calls+1;if calls<=4 then return false,'materials streaming' end;return real(self,ctx,skin) end
local r=require('reconcile').new()
for _,time in ipairs({100,103,109,121}) do assert(not r:update(a,core,a.config,c,nil,time)) end
assert(calls==4 and r.next_attempt==136)
for time=122,135 do r:update(a,core,a.config,c,nil,time) end;assert(calls==4)
assert(r:update(a,core,a.config,c,nil,136) and calls==5 and a:is_applied(c,s))
''')
check('native_material_refresh_and_std_restore_on_mission_instance', '''
local a,p,b,s=mission_fixture();local c=assert(a:mission_context())
local core=Core.new({schema_version=1,skins={s}}, {selections={[s.aircraft_id]=s.id}})
local r=require('reconcile').new();assert(r:update(a,core,a.config,c,nil,100))
local native=material('native-mission-skin-two',{BodyColor=object('native-mission-texture-two')})
b:SetMaterial(0,native);assert(not a:is_applied(c,s))
assert(r:update(a,core,a.config,c,nil,101) and a:is_applied(c,s))
core.saved.selections[s.aircraft_id]='original'
assert(r:update(a,core,a.config,c,nil,102));assert(b:GetMaterial(0)==native)
local writes=b.writes
for i=1,30 do r:update(a,core,a.config,c,nil,102+i) end;assert(b.writes==writes)
''')
check('new_mission_actor_resets_retry_backoff_and_dead_state_is_pruned', '''
local r=require('reconcile').new()
local a,p,b,s=mission_fixture('old');local c=assert(a:mission_context())
local core=Core.new({schema_version=1,skins={s}}, {selections={[s.aircraft_id]=s.id}})
local real=a.apply;a.apply=function() return false,'streaming' end
for _,time in ipairs({100,103,109,121}) do r:update(a,core,a.config,c,nil,time) end
local fresh,plane,body,skin=mission_fixture('new');local ctx=assert(fresh:mission_context())
assert(r:update(fresh,core,fresh.config,ctx,nil,122) and fresh:is_applied(ctx,skin))
body.IsValid=function() return false end;fresh:prune()
assert(next(fresh.applied)==nil and next(fresh.originals)==nil and next(fresh.components)==nil and next(fresh.textures)==nil)
''')
check('installed_hk_binding_slots_are_transactionally_applied', '''
local a,p,b,s=mission_fixture();local c=assert(a:mission_context())
local native10=material('su57-body-slot10',{BaseColor=object('su57-native')})
local native13=material('su57-emissive-slot13',{BaseColor=object('su57-native')})
b.materials[10],b.materials[13]=native10,native13
s.bindings={{target='body',material_index=10,parameter='BaseColor',texture=s.resource_root..'Texture_001.T_PP0021_su57_001_C'},
    {target='body',material_index=13,parameter='BaseColor',texture=s.resource_root..'Texture_001.T_PP0021_su57_001_C'}}
assert(a:apply(c,s) and a:is_applied(c,s))
assert(b:GetMaterial(10)~=native10 and b:GetMaterial(13)~=native13)
assert(a:apply(c,{id='original',aircraft_id=s.aircraft_id}))
assert(b:GetMaterial(10)==native10 and b:GetMaterial(13)==native13)
''')

# Exercise the actual main.lua loops through menu -> flight -> restart -> menu.
with tempfile.TemporaryDirectory(prefix='ac8-mission-entry-') as directory:
    root = Path(directory) / 'AC8SkinManager'
    shutil.copytree(PROJECT / 'src', root / 'Scripts')
    shutil.copy2(PROJECT / 'vendor/json.lua', root / 'Scripts/json.lua')
    (root / 'catalog.json').write_text('{"schema_version":1,"aircraft":[],"skins":[]}', encoding='utf-8')
    (root / 'config.json').write_text('{"runtime_switch_enabled":true,"package_registration_enabled":false}', encoding='utf-8')
    vm.execute('''
entry_adapter,entry_plane,entry_body,entry_skin,entry_native,entry_hangar=mission_fixture('entry')
entry_hangar.component=entry_body
entry_mode='hangar';entry_now=100
os.time=function() return entry_now end
function entry_adapter:context() if entry_mode=='hangar' then self.last_aircraft_id=entry_skin.aircraft_id;return entry_hangar end end
package.loaded.adapter={new=function(config) entry_adapter.config=config;return entry_adapter end}
package.loaded.registry={discover=function() return {entry_skin} end}
package.loaded.menu={new=function() return {render=function(self,core,ctx) self.panel=ctx and {};entry_core=core;entry_visible=ctx~=nil;return true end,
    hide=function(self) self.panel=nil end,poll=function() end} end}
entry_adapter.native_skin_page=function() return nil end
IterateGameDirectories=function() return {Game={Binaries={Win64={ue4ss={Mods={AC8SkinManager={Skins={}}}}}}}} end
ExecuteInGameThread=function(fn) fn() end
loops={};LoopAsync=function(ms,fn) loops[ms]=fn end
Key={F6=117,F7=118,F9=120,F10=121,F11=122}
IsKeyBindRegistered=function() return false end;RegisterKeyBind=function() end
NotifyOnNewObject=function() end;print=function() end
''')
    selected_id = vm.globals().entry_skin['id']
    (root / 'selections.json').write_text(json.dumps({'selections': {'PP0021_su57': selected_id}}), encoding='utf-8')
    vm.execute('dofile(...)', (root / 'Scripts/main.lua').as_posix())
    vm.execute('''
loops[1200]();assert(entry_visible and entry_adapter:is_applied(entry_hangar,entry_skin))
-- A new task actor starts with native materials, while the UI vanishes.
entry_mode='mission'
local native=material('mission-native',{BodyColor=object('mission-native-texture')})
entry_body.materials[0]=native
for _=1,3 do entry_now=entry_now+4;loops[1200]() end
local mission=assert(entry_adapter:mission_context())
assert(not entry_visible and entry_adapter:is_applied(mission,entry_skin))
local writes=entry_body.writes
for _=1,30 do entry_now=entry_now+4;loops[1200]();loops[33]() end
assert(entry_body.writes==writes)
-- Restart: component identity changes; no click or F6 is needed.
entry_body.GetFullName=function() return 'SkeletalMeshComponent /Game/Maps/Ingame/Mission001.PlayerRestart.PlaneBodyMesh' end
entry_body.materials[0]=native;entry_adapter.discovery_dirty=true
for _=1,3 do entry_now=entry_now+4;loops[1200]() end
assert(entry_adapter:is_applied(assert(entry_adapter:mission_context()),entry_skin) and not entry_visible)
entry_mode='hangar'
for _=1,3 do entry_now=entry_now+4;loops[1200]() end
assert(entry_visible and entry_core.saved.selections.PP0021_su57==entry_skin.id)
''')
    checks['entry_loops_handoff_to_flight_restart_return_and_hide_menu'] = True

for path in (PROJECT / 'src').glob('*.lua'):
    vm.execute('assert(loadfile(...))', path.as_posix())
checks['all_runtime_sources_parse'] = True
report = {'revision': '20261012-mission-restore', 'checks': checks,
          'scope': 'Isolated Lua regression tests, not an in-game rendering or performance result.'}
(PROJECT / 'mission-test-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
