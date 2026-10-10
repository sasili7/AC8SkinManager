-- Only manage the skin list owned by the native hangar skin page. Never
-- enable locked game content or disable the page's Back/navigation controls.
local NativeMode = {}
NativeMode.__index = NativeMode
local function valid(o)
    local ok, value = pcall(function() return o and o:IsValid() end)
    return ok and value == true
end
function NativeMode.new() return setmetatable({locked = {}}, NativeMode) end
function NativeMode:restore()
    for key, item in pairs(self.locked) do
        if valid(item.widget) then
            local ok = pcall(function() item.widget:SetIsEnabled(item.enabled) end)
            if ok then self.locked[key] = nil end
        else self.locked[key] = nil end
    end
end
function NativeMode:sync(adapter, core, enabled)
    if not enabled then self:restore(); return end
    local aircraft = adapter.last_aircraft_id
    local choice = aircraft and core.saved.selections[aircraft]
    local exists = false
    for _, skin in ipairs(core.catalog and core.catalog.skins or {}) do
        if skin.id == choice and skin.aircraft_id == aircraft and skin.status == "ready" then exists = true; break end
    end
    local applied = exists and ((adapter.owns_overrides and adapter:owns_overrides(aircraft, choice))
        or (not adapter.owns_overrides and adapter.has_applied and adapter:has_applied(aircraft, choice)))
    if not applied then self:restore(); return end
    local page = adapter:native_skin_page()
    -- No saved MOD choice means native authority. In particular, never force
    -- SetIsEnabled(true): restore only a state this component actually changed.
    if not page or not choice or choice == "original" then self:restore(); return end
    local ok, list = pcall(function() return page.WBP_Menu_SkinEmblem_ListView_000 end)
    if not ok or not valid(list) then return end
    local key = list:GetFullName()
    if self.locked[key] and not valid(self.locked[key].widget) then self.locked[key] = nil end
    if not self.locked[key] then
        local got, was_enabled = pcall(function() return list:GetIsEnabled() end)
        -- Do not take ownership of a native animation/unlock gate that is
        -- already disabled. Wait until the game itself enables this list.
        if not got or was_enabled ~= true then return end
        self.locked[key] = {widget = list, enabled = was_enabled}
    end
    pcall(function() if list:GetIsEnabled() then list:SetIsEnabled(false) end end)
end
return NativeMode
