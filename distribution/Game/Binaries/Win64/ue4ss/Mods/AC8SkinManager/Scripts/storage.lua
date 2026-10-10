-- Bounded, schema-checked reads. A broken settings file never stops the menu.
local Storage = {}
function Storage.config(value)
    if type(value) ~= "table" then return false end
    for _, key in ipairs({"runtime_switch_enabled", "package_registration_enabled", "diagnostic_self_test", "mission_switch_enabled"}) do
        if value[key] ~= nil and type(value[key]) ~= "boolean" then return false end
    end
    if value.hangar_widget_candidates ~= nil then
        if type(value.hangar_widget_candidates) ~= "table" or #value.hangar_widget_candidates > 16 then return false end
        for _, class in ipairs(value.hangar_widget_candidates) do
            if type(class) ~= "string" or not class:match("^[%w_]+$") or #class > 160 then return false end
        end
    end
    return true
end
function Storage.catalog(value)
    return type(value) == "table" and value.schema_version == 1 and type(value.aircraft) == "table"
        and type(value.skins) == "table"
end
function Storage.selections(value)
    return type(value) == "table" and type(value.selections) == "table"
end
function Storage.read(path, default, validate, json, log)
    local function attempt(file_path)
        local file = io.open(file_path, "rb")
        if not file then return nil, "missing" end
        local content = file:read(1048577); file:close()
        if not content or #content > 1048576 then return nil, "file too large" end
        local ok, value = pcall(json.decode, content:gsub("^\239\187\191", ""))
        if ok and validate(value) then return value end
        return nil, "invalid JSON or structure"
    end
    local value, why = attempt(path)
    if value then return value end
    local backup = attempt(path .. ".bak")
    if backup then
        if log then log(path .. "：已读取有效备份") end
        return backup
    end
    if why ~= "missing" and log then log(path .. "：配置无效，使用默认值；原文件保留") end
    return default
end
function Storage.write(path, value, json)
    local raw = json.encode(value)
    local file, err = io.open(path .. ".tmp", "wb")
    assert(file, err)
    local ok, why = file:write(raw); local closed, close_error = file:close()
    if not ok or not closed then os.remove(path .. ".tmp"); error(why or close_error) end
    -- Never replace the last good backup with an invalid primary.
    local old = io.open(path, "rb")
    if old then
        local text = old:read(1048577); old:close()
        local decoded, previous = pcall(json.decode, text or "")
        if decoded and Storage.selections(previous) then
            os.remove(path .. ".bak")
            local moved, move_error = os.rename(path, path .. ".bak")
            if not moved then os.remove(path .. ".tmp"); error(move_error) end
        else
            local moved, move_error = os.rename(path, path .. ".invalid-" .. tostring(os.time()))
            if not moved then os.remove(path .. ".tmp"); error(move_error) end
        end
    end
    local moved, move_error = os.rename(path .. ".tmp", path)
    if not moved then os.rename(path .. ".bak", path); error(move_error) end
end
return Storage
