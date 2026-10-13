"""Count engine work in real Lua code; these are not game FPS measurements."""
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
for filename, markers in [('test_framework.py', ('function manifest(', 'function object(', 'function context_fixture(')),
                          ('test_mission_restore.py', ('function mission_fixture(',))]:
    for node in ast.parse((PROJECT / filename).read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == 'execute' and call.args and isinstance(call.args[0], ast.Constant):
                source = call.args[0].value
                if isinstance(source, str) and any(marker in source for marker in markers):
                    vm.execute(source)

checks = {}
def check(name, source):
    vm.execute(source)
    checks[name] = True

check('stable_player_discovery_is_cached_with_30_second_fallback', '''
local a,p,b=mission_fixture();local now=100;os.time=function() return now end
local find=FindAllOf;local calls=0;FindAllOf=function(c) calls=calls+1;return find(c) end
assert(a:mission_context());assert(calls==1)
for i=1,29 do now=100+i;assert(a:mission_context()) end
assert(calls==1);now=130;assert(a:mission_context());assert(calls==2)
''')
check('hud_notifications_do_not_trigger_discovery_but_hangar_does', '''
local a,p,b=mission_fixture();os.time=function() return 100 end
assert(a:mission_context());a.last_hangar_check=100
local scans=a.mission_scans
for i=1,20 do a:queue_widget(object('WBP_Mission_HUD_C hud'..i));assert(a:flight_context()) end
assert(a.mission_scans==scans and not a.ui_rescan)
a:queue_widget(object('WBP_Menu_Hangar_AircraftSettings_000_C menu'))
assert(not a:flight_context() and a.ui_rescan)
''')
check('reused_visible_hangar_widget_exits_fast_path', '''
local a,p,b=mission_fixture();os.time=function() return 100 end
assert(a:mission_context());a.last_hangar_check=100
local w=object('existing-menu');w.IsVisible=function() return true end
a.config.hangar_widget_candidates={'KnownMenu'};a.object_cache.KnownMenu={objects={w},time=100}
assert(not a:flight_context())
''')
check('new_player_invalidates_cache_and_ambiguity_is_rejected', '''
local a,p,b=mission_fixture();assert(a:mission_context())
local other=object('LivePlayerPlane /Game/Maps/Ingame/New.Player')
FindAllOf=function(c) return c=='LivePlayerPlane' and {p,other} or {} end
a.mission_dirty=true
assert(not a:mission_context() and a.mission_discovery.state=='ambiguous-player')
assert(a.mission_players==nil)
''')
check('destroyed_player_and_delayed_body_recover_without_waiting_30_seconds', '''
local a,p,b=mission_fixture();assert(a:mission_context());p.IsValid=function() return false end
FindAllOf=function() return {} end;assert(not a:mission_context())
local fresh,np,nb=mission_fixture('new');assert(a:mission_context().pawn==np)
nb.IsValid=function() return false end;assert(not a:mission_context())
nb.IsValid=function() return true end;assert(a:mission_context().component==nb)
''')
check('cache_still_checks_owner_mesh_and_explicit_ai_flags', '''
local a,p,b=mission_fixture();assert(a:mission_context())
p.IsLocallyControlled=function() return false end;assert(not a:mission_context())
p.IsLocallyControlled=function() return true end;assert(a:mission_context())
b.GetSkeletalMeshAsset=function() return object('SkeletalMesh /Game/PP0018_fa36/Body') end
assert(a:mission_context().aircraft_id=='PP0018_fa36')
b.GetOwner=function() return object('someone-else') end;assert(not a:mission_context())
''')
check('notification_queue_has_a_bound_and_safe_fallback', '''
local a=mission_fixture();for i=1,1000 do a:queue_widget(object('HUD'..i)) end
assert(#a.new_widgets==32 and a.ui_rescan);a:consume_widgets();assert(a.new_widgets==nil)
''')

with tempfile.TemporaryDirectory(prefix='ac8-flight-performance-') as directory:
    root = Path(directory) / 'AC8SkinManager'
    shutil.copytree(PROJECT / 'src', root / 'Scripts')
    shutil.copy2(PROJECT / 'vendor/json.lua', root / 'Scripts/json.lua')
    (root / 'catalog.json').write_text('{"schema_version":1,"aircraft":[],"skins":[]}', encoding='utf-8')
    (root / 'config.json').write_text('{"runtime_switch_enabled":true,"package_registration_enabled":false}', encoding='utf-8')
    vm.execute('''
a,p,b,s,native,hangar=mission_fixture('long-flight')
now=100;os.time=function() return math.floor(now) end
context_calls=0;prunes=0;mode='mission';hangar.component=b
function a:context()
    context_calls=context_calls+1;self:consume_widgets();self.ui_rescan=false;self.last_hangar_check=os.time()
    if mode=='hangar' then self.last_aircraft_id=s.aircraft_id;return hangar end
end
local prune=a.prune;function a:prune() prunes=prunes+1;return prune(self) end
package.loaded.adapter={new=function(config) a.config=config;return a end}
package.loaded.registry={discover=function() return {s} end}
package.loaded.menu={new=function() return {render=function(self,core,ctx) self.panel=ctx and {};visible=ctx~=nil;return true end,
    hide=function(self) self.panel=nil end,poll=function() end} end}
a.native_skin_page=function() return nil end
IterateGameDirectories=function() return {Game={Binaries={Win64={ue4ss={Mods={AC8SkinManager={Skins={}}}}}}}} end
ExecuteInGameThread=function(fn) fn() end
loops={};LoopAsync=function(ms,fn) loops[ms]=fn end
Key={F6=117,F7=118,F9=120,F10=121,F11=122}
IsKeyBindRegistered=function() return false end;RegisterKeyBind=function() end
notifications={};NotifyOnNewObject=function(path,fn) notifications[path]=fn end;print=function() end
''')
    (root / 'selections.json').write_text(json.dumps({'selections': {'PP0021_su57': vm.globals().s['id']}}), encoding='utf-8')
    vm.execute('dofile(...)', (root / 'Scripts/main.lua').as_posix())
    vm.execute('loops[1200]();assert(a:is_applied(assert(a:mission_context()),s))')
    status = (root / 'menu-status.json').read_bytes()
    vm.execute('''
local writes=b.writes
for i=1,500 do
    now=now+1.2
    if i%10==0 then notifications['/Script/UMG.UserWidget'](object('WBP_Mission_HUD_C transient')) end
    loops[1200]();loops[33]()
end
assert(context_calls<=22 and a.mission_scans<=22 and prunes<=23)
assert(b.writes==writes and not visible)
flight_counts={seconds=600,hangar_discoveries=context_calls,player_scans=a.mission_scans,prunes=prunes}
''')
    assert (root / 'menu-status.json').read_bytes() == status, 'Stable flight rewrote status file'
    checks['ten_minute_flight_bounds_scans_and_avoids_status_and_material_writes'] = True
    counts = dict(vm.globals().flight_counts.items())
    vm.execute('''
-- The cached path must still repair an in-place texture reset.
b.materials[0].params.BodyColor=object('native-reset')
for i=1,3 do now=now+1.2;loops[1200]() end
assert(a:is_applied(assert(a:mission_context()),s))
-- A reused hangar is signalled on return, even if the old player survives.
mode='hangar';notifications['/Script/UMG.UserWidget'](object('WBP_Menu_Hangar_AircraftSettings_000_C return'))
for i=1,3 do now=now+1.2;loops[1200]() end
assert(visible and a.last_mission==nil)
''')
    checks['real_loops_repair_material_and_return_to_hangar'] = True

report = {'revision': '20261013-flight-cache', 'checks': checks, 'simulated_counts': counts,
          'scope': 'Engine-call counts with Lua fixtures; no measured game frame-time or FPS claims.'}
(PROJECT / 'flight-performance-test-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
