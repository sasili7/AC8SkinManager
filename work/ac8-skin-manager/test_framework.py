from pathlib import Path
import copy
import importlib.util
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'test-runtime'))
from lupa import LuaRuntime
from validate_skin import validate

OUT = ROOT.parents[1] / 'outputs/ac8-skin-manager'
STAGE = OUT / 'AC8-Skin-Manager-0.1.0-Interface'
MOD = STAGE / 'Game/Binaries/Win64/ue4ss/Mods/AC8SkinManager'
for source in (ROOT / 'src').glob('*.lua'):
    shutil.copy2(source, MOD / 'Scripts' / source.name)
lua = LuaRuntime(unpack_returned_tuples=True)
lua.globals().package.path = str(MOD / 'Scripts/?.lua').replace('\\', '/') + ';' + lua.globals().package.path
checks = {}

lua.execute(r'''
Core, Registry = require('core'), require('registry')
function manifest(plane, id, provider)
    return {schema_version=1, provider_id=provider or 'sample', id=id or 'blue', aircraft_id=plane or 'PP0021_su57',
        name='Blue', author='Author',status='ready',bindings={{target='body',material_index=0,parameter='BodyColor',
        texture='/Game/AC8SkinManager/Skins/'..(provider or 'sample')..'/'..(plane or 'PP0021_su57')..'/'..(id or 'blue')..'/T_C.T_C'}}}
end
function state()
    local skins=Registry.collect({{data=manifest('PP0021_su57')},{data=manifest('PP0022_f16c')}}, error)
    local writes=0
    local c=Core.new({schema_version=1,skins=skins}, {selections={}},function() writes=writes+1 end)
    local a={current='PP0021_su57',calls=0}
    function a:context() return {aircraft_id=self.current} end
    function a:apply(ctx,row) self.calls=self.calls+1;self.last=row.id;return true,'Applied',function() self.undone=true end end
    return c,a,function() return writes end
end
''')

def check(name, source):
    lua.execute(source)
    checks[name] = True

check('aircraft_filtering_and_independent_saved_selection', '''
local c,a,w=state();c:set_aircraft('PP0021_su57');c:toggle();c:move(1);assert(#c:rows()==2);assert(c:apply(a));
local su=c.saved.selections.PP0021_su57;assert(su:find('PP0021_su57'));
a.current='PP0022_f16c';c:set_aircraft(a.current);assert(c.cursor==1);c:move(1);assert(c:apply(a));
assert(c.saved.selections.PP0021_su57==su);assert(c.saved.selections.PP0022_f16c~=su);assert(w()==2)
''')
check('selection_preserved_when_returning_to_aircraft', '''
local c,a=state();c:set_aircraft(a.current);c:toggle();c:move(1);assert(c:apply(a));
c:set_aircraft('PP0022_f16c');c:set_aircraft('PP0021_su57');assert(c.cursor==2)
''')
check('leaving_preparation_closes_menu_and_does_not_apply', '''
local c,a=state();c:set_aircraft(a.current);c:toggle();c:set_aircraft(nil);assert(not c.opened);assert(not c:apply(a));assert(a.calls==0)
''')
check('aircraft_change_during_apply_rejected', '''
local c,a=state();c:set_aircraft(a.current);c:toggle();c:move(1);a.current='PP0022_f16c';assert(not c:apply(a));assert(a.calls==0)
''')
check('draft_skin_never_reaches_material_adapter', '''
local c,a=state();c.catalog.skins[1].status='requires_conversion';
c:set_aircraft(c.catalog.skins[1].aircraft_id);a.current=c.aircraft;c:toggle();c:move(1);assert(not c:apply(a));assert(a.calls==0)
''')
check('failed_material_apply_never_saved', '''
local c,a,w=state();function a:apply() return false,'No binding' end
c:set_aircraft(a.current);c:toggle();c:move(1);assert(not c:apply(a));assert(w()==0);assert(next(c.saved.selections)==nil)
assert(c.applied_skin=='original')
''')
check('failed_persistence_restores_previous_state_and_undo', '''
local c,a=state();c.persist=function() error('Read-only storage') end
c:set_aircraft(a.current);c:toggle();c:move(1);assert(not c:apply(a));assert(a.undone);assert(next(c.saved.selections)==nil)
assert(c.applied_skin=='original')
''')
check('failed_switch_keeps_previous_applied_skin_highlight', '''
local c,a=state();c:set_aircraft(a.current);c:toggle();c:move(1);assert(c:apply(a))
local selected=c.applied_skin;assert(selected~='original')
c.cursor=1;function a:apply() return false,'Apply failed' end
assert(not c:apply(a));assert(c.applied_skin==selected and c.saved.selections[c.aircraft]==selected)
function a:apply() return true,'Applied',function() self.undone=true end end
c.persist=function() error('Save failed') end
assert(not c:apply(a));assert(a.undone and c.applied_skin==selected and c.saved.selections[c.aircraft]==selected)
''')
check('registry_accepts_same_local_id_for_different_aircraft', '''
local errors={};local r=Registry.collect({{data=manifest('PP0021_su57')},{data=manifest('PP0022_f16c')}},function(e) errors[#errors+1]=e end)
assert(#r==2 and #errors==0 and r[1].id~=r[2].id)
''')
check('registry_isolates_invalid_or_duplicate_author_manifests', '''
local errors={};local bad=manifest();bad.bindings[1].texture='/Game/Vehicles/Aircraft/Original'
local r=Registry.collect({{data=manifest()},{data=manifest()},{data=bad},{data=manifest('PP0022_f16c')}},function(e) errors[#errors+1]=e end)
assert(#r==2 and #errors==2)
''')
check('registry_rejects_cross_provider_and_duplicate_bindings', '''
local m=manifest();m.bindings[1].texture=m.bindings[1].texture:gsub('/sample/','/other/');assert(not pcall(Registry.normalize,m))
m=manifest();m.bindings[2]=m.bindings[1];assert(not pcall(Registry.normalize,m))
m=manifest();m.schema_version=2;assert(not pcall(Registry.normalize,m))
''')
lua.execute(r'''
function object(n)
    return {IsValid=function() return true end,GetFullName=function() return n end,IsA=function() return true end}
end
function material(n,params)
    local m=object(n);m.params=params or {}
    function m:IsA(class) return self.dynamic==true and class:GetFullName()=='/Script/Engine.MaterialInstanceDynamic' end
    function m:K2_GetTextureParameterValue(p) return self.params[p] end
    function m:SetTextureParameterValue(p,t) self.params[p]=t end
    function m:K2_CopyMaterialInstanceParameters(source)
        self.params={};for k,v in pairs(source.params) do self.params[k]=v end
    end
    return m
end
function fixture()
    local original=material('original',{BodyColor=object('original-texture')})
    original.dynamic=true;original.Parent=material('native-asset',original.params)
    local comp=object('body');comp.materials={[0]=original};comp.writes=0
    function comp:GetMaterial(i) return self.materials[i] end
    function comp:SetMaterial(i,m) self.materials[i]=m;self.writes=self.writes+1 end
    function comp:CreateDynamicMaterialInstance(i,source)
        -- The component helper may reuse an existing MID. Tests must model
        -- this behavior rather than silently giving the adapter a fresh copy.
        if source.dynamic then self:SetMaterial(i,source);return source end
        local params={};for k,v in pairs(source.params) do params[k]=v end
        local mid=material('mid-'..self.writes,params);self:SetMaterial(i,mid);return mid
    end
    FName=function(n) return n end
    local factory=object('KismetMaterialLibrary');local serial=0
    function factory:CreateDynamicMaterialInstance(component,parent)
        assert(not parent.dynamic, 'Dynamic parents must be unwrapped')
        serial=serial+1;local mid=material('isolated-'..serial,{});mid.dynamic=true;mid.Parent=parent;return mid
    end
    StaticFindObject=function(n)
        if n=='/Script/Engine.Default__KismetMaterialLibrary' then return factory end
        if n:sub(1,6)=='/Game/' then return nil end;return object(n)
    end
    LoadAsset=function(n) return object(n) end
    local Adapter=require('adapter');local a=Adapter.new({runtime_switch_enabled=true})
    local ctx={aircraft_id='PP0021_su57',fingerprint='body',component=comp,phase='preparation',offline_verified=true}
    function a:context() return ctx end
    local skin=Registry.normalize(manifest())
    return a,ctx,skin,comp,original
end
''')
check('runtime_gate_and_offline_gate_prevent_all_material_writes', '''
local a,c,s,b=fixture();a.config.runtime_switch_enabled=false;assert(not a:apply(c,s));assert(b.writes==0)
a.config.runtime_switch_enabled=true;c.offline_verified=nil;assert(not a:apply(c,s));assert(b.writes==0)
''')
check('material_switch_creates_independent_instance_and_restores_original', '''
local a,c,s,b,original=fixture();assert(a:apply(c,s));assert(b.materials[0]~=original)
assert(original.params.BodyColor:GetFullName()=='original-texture')
assert(a:apply(c,{id='original',aircraft_id=c.aircraft_id}));assert(b.materials[0]==original)
assert(original.params.BodyColor:GetFullName()=='original-texture')
''')
check('restore_failure_is_detected_by_actual_material_readback_and_rolled_back', '''
local a,c,s,b,original=fixture();assert(a:apply(c,s));local managed=b.materials[0]
local setter=b.SetMaterial
function b:SetMaterial(index,value) if value~=original then setter(self,index,value) end end
assert(not a:apply(c,{id='original',aircraft_id=c.aircraft_id}))
assert(b.materials[0]==managed and a:is_applied(c,s))
''')
check('material_failure_rolls_back_all_changed_slots', '''
local a,c,s,b,original=fixture();s.bindings[2]={material_index=0,parameter='MissingParam',texture=s.resource_root..'T_2.T_2'}
assert(not a:apply(c,s));assert(b.materials[0]==original);assert(original.params.BodyColor:GetFullName()=='original-texture')
''')
check('native_refresh_on_same_actor_is_detected_and_new_native_material_is_restored', '''
local a,c,s,b,original=fixture();assert(a:apply(c,s));assert(a:is_applied(c,s))
local native=material('native-new-skin',{BodyColor=object('native-new-texture')})
b:SetMaterial(0,native);assert(not a:is_applied(c,s))
assert(a:apply(c,s));assert(a:is_applied(c,s))
assert(a:apply(c,{id='original',aircraft_id=c.aircraft_id}));assert(b.materials[0]==native)
assert(a:is_applied(c,{id='original'}))
''')
check('readback_detects_parameter_replacement_without_material_replacement', '''
local a,c,s,b=fixture();assert(a:apply(c,s));assert(a:is_applied(c,s))
b.materials[0].params.BodyColor=object('native-reset-texture');assert(not a:is_applied(c,s))
assert(a:apply(c,s));assert(a:is_applied(c,s))
''')
check('switch_between_skins_with_disjoint_slots_clears_old_overrides_and_undo_restores_tracking', '''
local a,c,s,b,original=fixture();local other=material('original-slot1',{BodyColor=object('slot1-texture')})
b.materials[1]=other;assert(a:apply(c,s));local first=b.materials[0]
local second=Registry.normalize(manifest('PP0021_su57','red'))
second.bindings[1].material_index=1
local good,_,undo=a:apply(c,second);assert(good)
assert(b.materials[0]==original and b.materials[1]~=other and a:is_applied(c,second))
undo();assert(b.materials[0]==first and b.materials[1]==other and a:is_applied(c,s))
local good,_,undo_original=a:apply(c,{id='original',aircraft_id=c.aircraft_id});assert(good)
undo_original();assert(b.materials[0]==first and a:is_applied(c,s))
''')
check('asset_loading_failure_has_no_partial_material_changes', '''
local a,c,s,b=fixture();LoadAsset=function() return nil end;assert(not a:apply(c,s));assert(b.writes==0)
''')
check('native_registration_failure_prevents_material_writes', '''
local a,c,s,b=fixture();a.config.package_registration_enabled=true
assert(not a:apply(c,s));assert(b.writes==0)
a.root='test/';local getenv=os.getenv;os.getenv=function() return nil end
assert(not a:apply(c,s));assert(b.writes==0);os.getenv=getenv
''')
check('native_registration_waiting_retries_and_success_is_cached', '''
local a,c,s,b=fixture();a.config.package_registration_enabled=true;a.root='test/'
local getenv,loadlib,open,remove=os.getenv,package.loadlib,io.open,os.remove
os.remove=function() return true end
local called=0;local native_state='waiting'
os.getenv=function() return '1' end
package.loadlib=function(path,entry)
    assert(path=='test/Native/registrar.dll' and entry=='register_packages')
    return function() called=called+1 end
end
io.open=function(path,mode)
    assert(path=='test/Native/registrar-status.json' and mode=='rb')
    return {read=function() return require('json').encode({revision='20261008-cached-store',state=native_state}) end,
        close=function() end}
end
assert(not a:apply(c,s));assert(b.writes==0 and called==1)
native_state='registered';assert(a:apply(c,s));assert(called==2)
assert(a:apply(c,s));assert(called==2 and a.native_registry.ready)
os.getenv,package.loadlib,io.open,os.remove=getenv,loadlib,open,remove
''')
check('newly_mounted_texture_loads_without_an_asset_registry_entry', '''
local a,c,s,b=fixture();local calls=0;local registry_calls=0
local library=object('KismetSystemLibrary')
function library:MakeSoftObjectPath(path) return {path=path} end
function library:Conv_SoftObjPathToSoftObjRef(path) return {object_path=path.path} end
function library:LoadAsset_Blocking(reference)
    calls=calls+1;assert(reference.object_path==s.bindings[1].texture);return object(reference.object_path)
end
local find=StaticFindObject
StaticFindObject=function(path) if path=='/Script/Engine.Default__KismetSystemLibrary' then return library end;return find(path) end
LoadAsset=function() registry_calls=registry_calls+1;return nil,false,false end
assert(a:apply(c,s));assert(calls==1 and registry_calls==0)
assert(a:apply(c,s));assert(calls==1) -- loaded asset cache
''')
check('unregistered_texture_uses_explicit_package_export_without_soft_pointer', '''
local a,c,s,b=fixture();local calls=0
EFindName={FNAME_Add=1}
FName=function(value,mode) if value:find('/Game/',1,true) then assert(mode==1) end;return value end
local helpers=object('AssetRegistryHelpers');local find=StaticFindObject
function helpers:GetAsset(data)
    calls=calls+1;assert(data.PackageName..'.'..data.AssetName==s.bindings[1].texture)
    return object(s.bindings[1].texture)
end
StaticFindObject=function(path)
    if path=='/Script/AssetRegistry.Default__AssetRegistryHelpers' then return helpers end
    if path=='/Script/Engine.Default__KismetSystemLibrary' then error('Soft pointer fallback not needed') end
    return find(path)
end
LoadAsset=function() error('Registry lookup not needed') end
assert(a:apply(c,s));assert(calls==1)
assert(a:apply(c,s));assert(calls==1)
''')
lua.execute('''
function ui_fixture()
    local root=object('canvas');root.children={}
    function root:AddChildToCanvas(child)
        self.children[#self.children+1]=child
        local slot=object('slot')
        for _, method in ipairs({'SetAnchors','SetAlignment','SetPosition','SetSize','SetZOrder'}) do slot[method]=function() end end
        return slot
    end
    StaticConstructObject=function(class,outer)
        local o=object('widget')
        o.Font={Size=24};o.WidgetStyle={CheckBoxType=0};o.children={}
        for _, method in ipairs({'SetBrushColor','SetPadding','SetAutoWrapText','SetColorAndOpacity','SetContent',
            'SetFont','SetOrientation','SetScrollBarVisibility','SetScrollbarThickness','SetHeightOverride',
            'SetWidthOverride','SetJustification','SetSlotPadding','SetToolTipText'}) do o[method]=function() end end
        function o:SetHorizontalAlignment(value) self.halign=value end
        function o:SetVerticalAlignment(value) self.valign=value end
        function o:AddChild(child) self.children[#self.children+1]=child;return {} end
        o.AddChildToVerticalBox=o.AddChild
        function o:AddChildToUniformGrid(child,row,col)
            self.children[#self.children+1]={child=child,row=row,col=col}
            return {SetHorizontalAlignment=function(_,value) child.slot_halign=value end,
                SetVerticalAlignment=function(_,value) child.slot_valign=value end}
        end
        function o:AddChildToOverlay(child)
            self.children[#self.children+1]=child
            return {SetHorizontalAlignment=function(_,value) child.slot_halign=value end,
                SetVerticalAlignment=function(_,value) child.slot_valign=value end}
        end
        function o:SetRenderOpacity(value) self.opacity=value end
        function o:SetIsChecked(value) self.checked=value end
        function o:SetIsEnabled(value) self.enabled=value end
        function o:IsChecked() return self.checked end
        function o:SetText(text) self.value=text end
        function o:RemoveFromParent() self.removed=true end
        return o
    end
    FText=function(text) return text end
    -- CanvasPanel slot supports stretched anchors.
    local add=root.AddChildToCanvas
    function root:AddChildToCanvas(child) local slot=add(self,child);slot.SetOffsets=function() end;return slot end
    local tree=object('tree');tree.RootWidget=root
    return {aircraft_id='PP0021_su57',fingerprint='body',widget={WidgetTree=tree}},root
end
''')
check('native_button_grid_is_automatic_and_preserves_host_widget', '''
local c,a=state();c:set_aircraft(a.current);local ctx,root=ui_fixture();local menu=require('menu').new()
assert(menu:render(c,ctx));assert(menu.panel and #menu.buttons==2);assert(#root.children==1)
assert(menu:render(c,ctx));assert(#root.children==1)
local panel=menu.panel;ctx.ui_fingerprint='new-widget';assert(menu:render(c,ctx));assert(panel.removed)
local next_panel=menu.panel;menu:render(c,nil);assert(next_panel.removed);assert(menu.panel==nil)
assert(ctx.widget.WidgetTree.RootWidget==root)
''')
check('native_toggle_click_is_latched_once_between_polls', '''
local c,a=state();c:set_aircraft(a.current);local ctx=ui_fixture();local calls=0
local menu=require('menu').new(function(index,key) assert(index==2 and key==ctx.fingerprint);calls=calls+1 end)
assert(menu:render(c,ctx));menu.buttons[2].control.checked=true
menu:poll();menu:poll();assert(calls==1 and menu.buttons[2].control.checked==false)
menu:hide();menu:poll();assert(calls==1)
''')
check('native_checkbox_style_uses_reflected_fields_without_cpp_only_setter', '''
local c,a=state();c:set_aircraft(a.current);local ctx=ui_fixture()
local construct=StaticConstructObject
StaticConstructObject=function(class,outer)
    local o=construct(class,outer)
    o.SetWidgetStyle={} -- UE4SS returns an uncallable TrivialObject for this method.
    return o
end
local menu=require('menu').new();assert(menu:render(c,ctx))
assert(#menu.buttons==2)
for _,item in ipairs(menu.buttons) do
    assert(item.control.WidgetStyle.CheckBoxType==1)
    assert(item.control.WidgetStyle.Padding.Left==0)
end
''')
check('native_heading_inherits_game_section_font_and_size', '''
local c,a=state();c:set_aircraft(a.current);local ctx=ui_fixture()
local tree=ctx.widget.WidgetTree;local font={Size=19,FontObject='GameHeadingFont',TypefaceFontName='Regular'}
local source=object('existing-ammo-heading');source.Font=font;source.ColorAndOpacity={game_color=true}
source.IsVisible=function() return true end;source.GetOuter=function() return tree end
source.GetText=function() return {ToString=function() return '[WEAPONS AMMO]' end} end
local old_find=FindAllOf;FindAllOf=function(class) if class=='TextBlock' then return {source} end;return {} end
local construct=StaticConstructObject
StaticConstructObject=function(class,outer)
    local o=construct(class,outer);o.SetFont=function(self,value) self.applied_font=value end;return o
end
local menu=require('menu').new();assert(menu:render(c,ctx))
local title=menu.panel.children[1];assert(title.value=='[LIVERY]')
assert(title.applied_font==font and title.applied_font.Size==19)
FindAllOf=old_find
''')
check('three_han_characters_and_ascii_labels_with_author_colors', '''
local p=require('presentation');assert(p.label('久岛鸥')=='久岛鸥');assert(p.label('RUS')=='RUS');assert(p.label('A鸥B')=='A鸥B')
assert(not pcall(p.label,'久岛鸥号'));assert(not pcall(p.label,'ABCD'));assert(not pcall(p.label,'123'));assert(not pcall(p.label,''))
local white=p.normalize({text='鸥',background_color='#ffffff'},'Name');assert(white.text_color=='#101820')
local dark=p.normalize({text='RUS',background_color='#000000',text_color='#F0E9D0'},'Name');assert(dark.text_color=='#F0E9D0')
assert(not pcall(p.normalize,{background_color='red'},'Name'))
assert(p.normalize(nil,'久岛鸥 · 夏日').text=='久岛鸥')
''')

lua.execute('''
function context_fixture()
    local widget=object('WBP_Menu_Hangar_AircraftSettings_000_C menu')
    widget.IsInViewport=function() return false end;widget.IsVisible=function() return true end
    local comps={}
    function add_body(id,hidden,recent,mission)
        local owner=object('display-owner-'..id);owner.IsHidden=function() return hidden end
        local map=mission and '/Game/Maps/Ingame/Mission000' or '/Game/Maps/Hangar/PL_Hangar005'
        local kind=mission and 'BP_PlayerPlane_' or 'BP_DisplayPlane_'
        local comp=object('SkeletalMeshComponent '..map..'.'..kind..id..'_C_1.PlaneBodyMesh')
        comp.IsVisible=function() return true end;comp.GetOwner=function() return owner end
        comp.GetSkeletalMeshAsset=function() return object('SkeletalMesh /Game/Vehicles/Aircraft/PP/'..id..'/SK_'..id) end
        comp.WasRecentlyRendered=function() return recent end;comps[#comps+1]=comp;return comp
    end
    FindAllOf=function(class) if class=='SkeletalMeshComponent' then return comps end;if class=='KnownMenu' then return {widget} end;return {} end
    return require('adapter').new({hangar_widget_candidates={'KnownMenu'}}),widget,comps,add_body
end
''')
check('embedded_selection_without_viewport_flag_is_recognized', '''
local a,w,comps,add=context_fixture();add('PP0021_su57',false,true);add('PP0014_rflm',true,false)
local ctx=assert(a:context());assert(ctx.aircraft_id=='PP0021_su57')
''')
check('hidden_parent_and_mission_aircraft_are_excluded', '''
local a,w,comps,add=context_fixture();add('PP0021_su57',false,true,true)
local pending=a:context();assert(pending.aircraft_id==nil and pending.model_ready==false)
add('PP0022_f16c',false,true);local parent=object('hidden-parent');parent.IsVisible=function() return false end
w.GetParent=function() return parent end;assert(a:context()==nil)
''')
check('multiple_display_aircraft_require_unique_recent_rendering', '''
local a,w,comps,add=context_fixture();add('PP0021_su57',false,true);add('PP0014_rflm',false,false)
assert(a:context().aircraft_id=='PP0021_su57');comps[2].WasRecentlyRendered=function() return true end
local pending=a:context();assert(pending.aircraft_id=='PP0021_su57' and pending.interactive==false)
''')
check('model_transition_retains_panel_and_disables_stale_clicks', '''
local a,w,comps,add=context_fixture();add('PP0021_su57',false,true)
local first=a:context();comps[1].IsVisible=function() return false end
local pending=a:context();assert(pending.ui_fingerprint==first.ui_fingerprint and pending.model_ready==false)
local c=state();c:set_aircraft(first.aircraft_id);local ui,root=ui_fixture()
first.widget,pending.widget=ui.widget,ui.widget
local clicks=0;local menu=require('menu').new(function() clicks=clicks+1 end)
assert(menu:render(c,first));local panel=menu.panel
assert(menu:render(c,pending));assert(menu.panel==panel and #root.children==1)
for _,item in ipairs(menu.buttons) do assert(item.control.enabled==false) end
menu.buttons[2].control.checked=true;menu:poll();assert(clicks==0)
assert(not a:apply(pending,{aircraft_id=first.aircraft_id}))
comps[1].IsVisible=function() return true end
local ready=a:context();ready.widget=ui.widget;assert(menu:render(c,ready))
assert(menu.panel==panel and menu.buttons[2].control.enabled==true)
w.IsVisible=function() return false end;assert(a:context()==nil and a.last_context==nil)
''')
check('weapon_and_native_skin_pages_hide_livery_even_with_visible_selection_parent', '''
local a,w,comps,add=context_fixture();add('PP0021_su57',false,true)
assert(a:context())
local native_find=FindAllOf
local weapon=object('WBP_Menu_Hangar_WeaponSettings1_000_C weapon')
weapon.IsVisible=function() return true end
FindAllOf=function(class)
    if class=='WBP_Menu_Hangar_WeaponSettings1_000_C' then return {weapon} end
    return native_find(class)
end
a.discovery_dirty=true -- new widget construction invalidates the discovery cache
assert(not a:selection_page_visible() and a:context()==nil)
weapon.IsVisible=function() return false end
assert(a:selection_page_visible() and a:context())
local skin=object('WBP_Menu_Hangar_AircraftSettings_Select_002_C native-skin-page')
skin.IsVisible=function() return true end
local with_weapon=FindAllOf
FindAllOf=function(class)
    if class=='WBP_Menu_Hangar_AircraftSettings_Select_002_C' then return {skin} end
    return with_weapon(class)
end
a.discovery_dirty=true
assert(a:context()==nil)
skin.IsVisible=function() return false end;assert(a:context())
''')
check('legacy_config_cannot_mount_the_livery_panel_on_a_weapon_page', '''
local a,w,comps,add=context_fixture();add('PP0021_su57',false,true)
a.config.hangar_widget_candidates={'WBP_Menu_Hangar_WeaponSettings1_000_C'}
local native_find=FindAllOf
FindAllOf=function(class)
    if class=='KnownMenu' then return {} end
    if class=='WBP_Menu_Hangar_WeaponSettings1_000_C' then return {w} end
    return native_find(class)
end
assert(a:context()==nil)
''')
check('detail_aircraft_resolves_overlap_and_excludes_wingman_text', '''
local a,w,comps,add=context_fixture();add('PP0021_su57',false,true);add('PP0014_rflm',false,true)
local function label(path,text)
    local b=object('TextBlock menu.WidgetTree.WBP_MenuCommon_HangarDetail_000.'..path)
    b.IsVisible=function() return true end;b.GetText=function() return {ToString=function() return text end} end
    return b
end
local selected=label('PlaneName','| Su-57 Felon |')
local wingman=label('SquadronWidget.Name','Rafale M')
local find=FindAllOf;FindAllOf=function(class) if class=='TextBlock' then return {selected,wingman} end;return find(class) end
a.aircraft={{id='PP0021_su57',name='Su-57'},{id='PP0014_rflm',name='Rafale M'}}
assert(a:context().aircraft_id=='PP0021_su57')
selected.GetText=function() return {ToString=function() return 'Rafale M' end} end
assert(a:context().aircraft_id=='PP0014_rflm')
comps[2].IsVisible=function() return false end
local pending=a:context();assert(pending.aircraft_id=='PP0014_rflm' and pending.interactive==false)
''')
check('small_skin_sets_reserve_four_columns_with_larger_click_targets', '''
local c,a=state();c:set_aircraft(a.current);local ctx=ui_fixture();local nodes={}
local construct=StaticConstructObject
StaticConstructObject=function(class,outer)
    local o=construct(class,outer);nodes[#nodes+1]=o
    o.SetHeightOverride=function(self,v) self.height=v end
    o.SetWidthOverride=function(self,v) self.width=v end
    o.SetFont=function(self,v) self.applied_size=v.Size end
    return o
end
local menu=require('menu').new();assert(menu:render(c,ctx))
local fourth,large,label=false,false,false
for _,o in ipairs(nodes) do
    for _,slot in ipairs(o.children) do
        if slot.col==3 then fourth=true;assert(slot.child.height==34) end
    end
    if o.height==34 and o.width>=49 then large=true end
    if o.value=='久岛鸥' then label=true;assert(o.applied_size>=12) end
end
assert(fourth and large)
''')
check('button_size_scales_with_the_actual_game_font_without_modifying_it', '''
local c,a=state();c:set_aircraft(a.current);local ctx=ui_fixture()
local tree=ctx.widget.WidgetTree;local source=object('native-section')
source.Font={Size=40,FontObject='NativeGameFont'};source.ColorAndOpacity={}
source.IsVisible=function() return true end;source.GetOuter=function() return tree end
source.GetText=function() return {ToString=function() return '[WEAPONS AMMO]' end} end
FindAllOf=function(class) if class=='TextBlock' then return {source} end;return {} end
local construct=StaticConstructObject
StaticConstructObject=function(class,outer)
    local o=construct(class,outer)
    o.SetFont=function(self,font) self.Font={};for k,v in pairs(font) do self.Font[k]=v end end
    return o
end
local menu=require('menu').new();assert(menu:render(c,ctx))
assert(menu.layout.font_size==38 and menu.layout.button_height==84)
assert(menu.layout.button_width>=124 and source.Font.Size==40)
for _,item in ipairs(menu.buttons) do assert(item.control.HorizontalAlignment==0) end
''')
check('flat_buttons_hide_native_checkbox_and_highlight_only_applied_skin_without_tooltips', '''
local c,a=state();c:set_aircraft(a.current);local ctx=ui_fixture()
local construct=StaticConstructObject
StaticConstructObject=function(class,outer)
    local o=construct(class,outer)
    o.SetToolTipText=function() error('Hover descriptions must not be installed') end
    o.SetBrushColor=function(self,color) self.color=color end
    return o
end
local menu=require('menu').new();assert(menu:render(c,ctx))
for _,item in ipairs(menu.buttons) do assert(item.control.opacity==0 and item.fill~=item.control) end
for _,item in ipairs(menu.buttons) do
    assert(item.fill.slot_halign==0 and item.fill.slot_valign==0)
    assert(item.control.slot_halign==0 and item.control.slot_valign==0)
    assert(item.outline.halign==0 and item.outline.valign==0)
    assert(item.fill.halign==0 and item.fill.valign==2)
end
assert(menu.buttons[1].outline.color.A==1 and menu.buttons[1].fill.color.A==1)
c.cursor=2;assert(menu:refresh(c));assert(menu.buttons[1].outline.color.A==1 and menu.buttons[2].outline.color.A==0.5)
c.opened=true;assert(c:apply(a));assert(menu:refresh(c))
assert(menu.buttons[2].outline.color.A==1 and menu.buttons[2].fill.color.A==1)
assert(menu.buttons[1].outline.color.A==0.5 and menu.buttons[1].fill.color.A==0.78)
''')
check('native_menu_unknown_mount_point_cleans_up_its_own_widgets', '''
local c,a=state();c:set_aircraft(a.current);c:toggle();local ctx,root=ui_fixture()
root.IsA=function() return false end;local menu=require('menu').new();assert(not menu:render(c,ctx));assert(menu.panel==nil)
assert(ctx.widget.WidgetTree.RootWidget==root)
''')

template = json.loads((STAGE / 'SDK/ExampleSkin/skin.json').read_text(encoding='utf-8'))
assert not validate(template)
ready = {**template, 'status': 'ready', 'bindings': [json.loads((STAGE / 'SDK/binding.example.json').read_text())]}
assert not validate(ready)
for change in [
    {'schema_version': 2}, {'provider_id': '../escape'}, {'aircraft_id': 'Su-57'},
    {'status': 'ready', 'bindings': []}, {'name': '鸥' * 80}, {'bindings': 'bad'},
]:
    assert validate({**template, **change}), change
bad = copy.deepcopy(ready)
bad['bindings'][0]['texture'] = '/Game/Other/T_C.T_C'
assert validate(bad)
for text_value in ['久岛鸥', 'RUS', 'A鸥B']:
    assert not validate({**template, 'button': {'text': text_value}})
for button_value in [{'text':'久岛鸥号'}, {'text':'ABCD'}, {'text':'123'}, {'text':''}, {'text':'😺'}, {'background_color':'red'}, {'text_color':'#FFF'}, []]:
    assert validate({**template, 'button':button_value}), button_value
checks['author_validator_enforces_unicode_button_labels_and_hex_colors'] = True
checks['author_cli_validates_template_utf8_limits_and_rejects_invalid_namespace'] = True

# Load the real entry script against read-only engine stubs in an isolated copy.
fixture_root = Path(tempfile.mkdtemp(prefix='framework-entry-', dir=ROOT))
fixture_mod = fixture_root / 'Game/Binaries/Win64/ue4ss/Mods/AC8SkinManager'
shutil.copytree(MOD, fixture_mod)
vm = LuaRuntime(unpack_returned_tuples=True)
vm.globals().fixture_root = str(fixture_root).replace('\\', '/')
vm.execute('''
local name='skin.json'
local manifest=fixture_root..'/Game/Binaries/Win64/ue4ss/Mods/AC8SkinManager/Skins/sasili/PP0021_su57/kamome/skin.json'
local skin={__files={{__name=name,__absolute_path=manifest}}}
local dir={Game={Binaries={Win64={__absolute_path=fixture_root..'/Game/Binaries/Win64',ue4ss={Mods={AC8SkinManager={Skins={sasili={PP0021_su57={kamome=skin}}}}}}}}}}
IterateGameDirectories=function() return dir end
FindAllOf=function() return {} end
EGameThreadMethod={EngineTick=0,ProcessEvent=1};ProcessEventAvailable=true
dispatch_calls=0
ExecuteInGameThread=function(fn,method) assert(method==1);dispatch_calls=dispatch_calls+1;fn() end
loops={};LoopAsync=function(ms,fn) loops[ms]=fn end
Key={F6=117,F7=118,F9=120,F10=121,F11=122}
callbacks={}
IsKeyBindRegistered=function(key) return callbacks[key]~=nil end
RegisterKeyBind=function(key,fn) callbacks[key]=fn end
print=function() end
''')
vm.execute('dofile(...)', str(fixture_mod / 'Scripts/main.lua').replace('\\', '/'))
vm.execute('for _, fn in pairs(callbacks) do fn() end; loops[1200](); loops[33](); assert(callbacks[117] and callbacks[122]); assert(dispatch_calls>0)')
assert (fixture_mod / 'interface-probe.txt').exists()
assert not (fixture_mod / 'selections.json').exists()
checks['entry_script_registers_keys_and_probe_without_game_or_skin_mutation'] = True
status = json.loads((fixture_mod / 'menu-status.json').read_text(encoding='utf-8'))
assert status['state'] == 'waiting' and status['dispatcher'] == 'ProcessEvent'
assert status['discovery']['candidate_widgets'] == 0
checks['entry_dispatch_uses_explicit_process_event_and_records_context_gate'] = True
vm.execute('''
local previous=ExecuteInGameThread
ExecuteInGameThread=function() error('dispatch unavailable') end
for _=1,3 do loops[1200]() end
ExecuteInGameThread=previous
''')
status = json.loads((fixture_mod / 'menu-status.json').read_text(encoding='utf-8'))
assert status['state'] == 'dispatch-failed'
vm.execute('for _=1,3 do loops[1200]() end')
assert json.loads((fixture_mod / 'menu-status.json').read_text(encoding='utf-8'))['state'] == 'waiting'
checks['entry_dispatch_failure_releases_pending_flag_for_retry'] = True
vm.execute('''
local previous,time=ExecuteInGameThread,os.time
local queued,callback=0,nil;local now=100
os.time=function() return now end
ExecuteInGameThread=function(fn,method) assert(method==1);queued=queued+1;callback=fn end
for _=1,3 do loops[1200]() end;now=110;for _=1,6 do loops[1200]() end;assert(queued==1)
callback();for _=1,3 do loops[1200]() end;assert(queued==2);callback()
ExecuteInGameThread=previous;os.time=time
''')
checks['entry_stalled_dispatch_does_not_queue_overlapping_uobject_actions'] = True

# Exercise the real periodic restore path against a transient native load and
# a subsequent native material refresh on the same display actor.
(fixture_mod / 'config.json').write_text(json.dumps({'runtime_switch_enabled': True}), encoding='utf-8')
(fixture_mod / 'selections.json').write_text(json.dumps({'selections': {'PP0021_su57': 'test'}}), encoding='utf-8')
vm.execute('''
local row={id='test',aircraft_id='PP0021_su57',name='Test',status='ready'}
package.loaded.registry={discover=function() return {row} end}
package.loaded.adapter={new=function()
    test_adapter={calls=0,applied=false,fail=true,textures={}}
    function test_adapter:context()
        local id=self.current or 'PP0021_su57';self.last_aircraft_id=id
        if self.absent then return nil end
        return {aircraft_id=id,fingerprint=id..'|body',ui_fingerprint=id..'|ui',model_ready=true}
    end
    function test_adapter:native_skin_page() return nil end
    function test_adapter:apply(ctx,skin)
        self.calls=self.calls+1
        if self.fail then return false,'transient load' end
        self.applied=skin.id=='test';return true,'Applied'
    end
    function test_adapter:is_applied(ctx,skin) return skin.id=='original' and not self.applied or skin.id=='test' and self.applied end
    return test_adapter
end}
package.loaded.menu={new=function()
    test_menu={render=function(self,core,ctx) self.panel=ctx and {};observed_core=core;observed_context=ctx;return true end,
        hide=function() end,poll=function() end}
    return test_menu
end}
test_now=100;os.time=function() return test_now end
''')
vm.execute('dofile(...)', str(fixture_mod / 'Scripts/main.lua').replace('\\', '/'))
vm.execute('''
loops[1200]();assert(test_adapter.calls==1 and observed_core.applied_skin=='')
test_now=101;loops[1200]();assert(test_adapter.calls==1)
test_now=104;test_adapter.fail=false;loops[1200]();assert(test_adapter.calls==2 and observed_core.applied_skin=='test')
test_now=106;loops[1200]();assert(test_adapter.calls==2)
test_adapter.applied=false;test_now=108;loops[1200]();assert(test_adapter.calls==3 and observed_core.applied_skin=='test')
''')
checks['entry_restore_retries_transient_failures_and_reapplies_after_native_refresh'] = True

(fixture_mod / 'config.json').write_text(json.dumps({'runtime_switch_enabled': True, 'diagnostic_self_test': True}), encoding='utf-8')
vm.execute('dofile(...)', str(fixture_mod / 'Scripts/main.lua').replace('\\', '/'))
vm.execute('test_adapter.fail=false;loops[1200]();assert(test_adapter.calls==6 and observed_core.applied_skin=="test")')
diagnostic = json.loads((fixture_mod / 'switch-diagnostic.json').read_text(encoding='utf-8'))
assert diagnostic['passed'] and diagnostic['restored_original'] and len(diagnostic['steps']) == 4
assert json.loads((fixture_mod / 'selections.json').read_text())['selections']['PP0021_su57'] == 'test'
checks['entry_roundtrip_diagnostic_restores_material_and_preserves_saved_choice'] = True

vm.execute('''
test_adapter.current='PP0022_f16c'
for _=1,8 do loops[33]() end
assert(observed_context.aircraft_id=='PP0022_f16c' and observed_core.aircraft=='PP0022_f16c')
test_adapter.current='PP0021_su57';test_adapter.applied=false;test_now=200
for _=1,8 do loops[33]() end
assert(observed_core.applied_skin=='test' and test_adapter.applied)
test_adapter.absent=true
for _=1,8 do loops[33]() end
assert(observed_context==nil and observed_core.aircraft==nil)
''')
checks['fast_poll_updates_aircraft_restores_saved_skin_and_hides_without_hotkey'] = True

vm.execute('''
test_adapter.absent=false;test_adapter.current='PP0021_su57';test_adapter.applied=false;test_adapter.fail=true;test_adapter.calls=0
for i=1,15 do test_now=300+i*4;loops[1200]() end
assert(test_adapter.calls>=4 and test_adapter.calls<=6)
local before=test_adapter.calls
test_menu.on_click(2,'PP0021_su57|ui');assert(test_adapter.calls==before+1)
test_now=500;loops[1200]();assert(test_adapter.calls==before+2)
''')
checks['automatic_restore_uses_backoff_and_manual_click_permits_immediate_retry'] = True

vm.execute('''
local execute=ExecuteInGameThread;local queued,callback=0,nil
ExecuteInGameThread=function(fn) queued=queued+1;callback=fn end
loops[1200]();for _=1,100 do loops[33]() end;assert(queued==1)
callback();loops[33]();assert(queued==2)
loops[1200]();assert(queued==2);callback()
ExecuteInGameThread=execute
''')
checks['background_and_input_dispatchers_do_not_overlap'] = True

vm.execute('''
observed_core.saved.selections.PP0021_su57='original'
test_adapter.absent=false;test_adapter.current='PP0021_su57';test_adapter.applied=false;test_adapter.calls=0
for i=1,20 do test_now=1000+i*4;loops[1200]() end
assert(test_adapter.calls==0 and observed_core.applied_skin=='original')
''')
checks['std_mode_does_not_reapply_materials_over_native_selection'] = True

check('native_skin_authority_restores_only_owned_list_state_and_respects_existing_locks', '''
local mode=require('native_mode').new()
local list=object('skin-list');list.enabled=true;list.writes=0
function list:GetIsEnabled() return self.enabled end
function list:SetIsEnabled(value) self.enabled=value;self.writes=self.writes+1 end
local page={WBP_Menu_SkinEmblem_ListView_000=list}
local adapter={last_aircraft_id='PP0021_su57',native_skin_page=function() return page end,has_applied=function() return true end}
local core={catalog={skins={{id='test',aircraft_id='PP0021_su57',status='ready'}}},saved={selections={PP0021_su57='original'}}}
mode:sync(adapter,core,true);assert(list.enabled and list.writes==0)
core.saved.selections.PP0021_su57='test'
mode:sync(adapter,core,true);assert(not list.enabled)
mode:sync(adapter,core,true)
core.saved.selections.PP0021_su57='original'
mode:sync(adapter,core,true);assert(list.enabled and next(mode.locked)==nil)
-- Native changes are preserved while original owns the skin.
list.enabled=false;mode:sync(adapter,core,true);assert(not list.enabled)
core.saved.selections.PP0021_su57='test';mode:sync(adapter,core,true)
core.saved.selections.PP0021_su57='original';mode:sync(adapter,core,true)
assert(not list.enabled)
list.enabled=true;core.saved.selections.PP0021_su57='test';mode:sync(adapter,core,true)
page=nil;mode:sync(adapter,core,true);assert(list.enabled)
''')

check('detached_valid_livery_panel_is_reattached_on_automatic_render', '''
local c,a=state();c:set_aircraft(a.current);local ctx,root=ui_fixture()
local menu=require('menu').new();assert(menu:render(c,ctx));local old=menu.panel
old.GetParent=function() return nil end
assert(menu:render(c,ctx) and menu.panel~=old)
''')

for path in (MOD / 'Scripts').glob('*.lua'):
    lua.execute('assert(loadfile(...))', str(path).replace('\\', '/'))
checks['all_shipped_lua_files_parse'] = True

report = {'version': '0.1.0-interface', 'scope': 'Offline Lua engine mocks, registry, author validator and entry-script checks; not a game integration result.', 'checks': checks}
(ROOT / 'test-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
