-- Pure state machine: no engine calls and no arbitrary code loaded from skins.
local Core = {}
Core.__index = Core

local function valid_id(id)
    return type(id) == "string" and #id <= 192 and id:match("^[%w_%-]+$") ~= nil
end

function Core.new(catalog, saved, persist)
    assert(type(catalog) == "table" and catalog.schema_version == 1, "皮肤目录格式不正确")
    local self = setmetatable({catalog = catalog, saved = type(saved) == "table" and saved or {}, persist = persist,
        aircraft = nil, cursor = 1, opened = false, applied_skin = "original", status = "F6 打开涂装菜单"}, Core)
    if type(self.saved.selections) ~= "table" then self.saved.selections = {} end
    local ids, planes = {}, {}
    for _, plane in ipairs(catalog.aircraft or {}) do
        if type(plane) == "table" and valid_id(plane.id) then planes[plane.id] = true end
    end
    for _, skin in ipairs(catalog.skins or {}) do
        assert(valid_id(skin.id) and valid_id(skin.aircraft_id), "皮肤或机型编号不正确")
        assert(skin.id ~= "original" and not ids[skin.id], "皮肤编号重复或使用保留编号")
        ids[skin.id] = skin.aircraft_id; planes[skin.aircraft_id] = true
        assert(type(skin.name) == "string" and #skin.name < 240, "皮肤名称不正确")
    end
    for aircraft, choice in pairs(self.saved.selections) do
        if not valid_id(aircraft) or not planes[aircraft]
            or (choice ~= "original" and ids[choice] ~= aircraft) then self.saved.selections[aircraft] = nil end
    end
    return self
end

function Core:rows()
    local result = {{id = "original", name = "Standard", aircraft_id = self.aircraft, status = "original"}}
    for _, skin in ipairs(self.catalog.skins or {}) do
        if skin.aircraft_id == self.aircraft then result[#result + 1] = skin end
    end
    return result
end

function Core:set_aircraft(id)
    if id ~= nil and not valid_id(id) then return false end
    if self.aircraft == id then return false end
    self.aircraft = id
    self.applied_skin = "original"
    self.cursor = 1
    local selected = self.saved.selections[id or ""]
    for i, row in ipairs(self:rows()) do if row.id == selected then self.cursor = i end end
    self.status = id and "选择涂装后按 F11 应用" or "请先在出发准备界面选中一架飞机"
    if not id then self.opened = false end
    return true
end

function Core:toggle()
    if not self.aircraft then return false, "未识别当前飞机" end
    self.opened = not self.opened
    return self.opened
end

function Core:move(delta)
    if not self.opened then return false end
    local count = #self:rows()
    self.cursor = ((self.cursor - 1 + delta) % count) + 1
    return true
end

function Core:apply(adapter)
    if not self.opened or not self.aircraft then return false, "请先打开涂装菜单" end
    local row = self:rows()[self.cursor]
    local ctx, why = adapter:context()
    if not ctx or ctx.aircraft_id ~= self.aircraft then
        self.status = "选中的飞机已变化，请重新打开菜单"
        return false, why or self.status
    end
    if row.aircraft_id ~= self.aircraft then return false, "皮肤与当前机型不匹配" end
    if row.id ~= "original" and row.status ~= "ready" then
        self.status = "此皮肤需要转换为游戏内切换格式"
        return false, self.status
    end
    local ok, message, undo = adapter:apply(ctx, row)
    if not ok then self.status = message or "换肤接口尚未接通"; return false, self.status end
    local previous = self.saved.selections[self.aircraft]
    self.saved.selections[self.aircraft] = row.id
    local write_ok, write_message = pcall(self.persist, self.saved)
    if not write_ok then
        self.saved.selections[self.aircraft] = previous
        if undo then pcall(undo) end
        self.status = "保存失败，已撤销本次操作：" .. tostring(write_message)
        return false, self.status
    end
    self.applied_skin = row.id
    self.status = message or ("已应用：" .. row.name)
    return true, self.status
end

function Core:label()
    for _, plane in ipairs(self.catalog.aircraft or {}) do
        if plane.id == self.aircraft then return plane.name end
    end
    return self.aircraft or "未选择飞机"
end

return Core
