-- Optional author button metadata. Older API v1 manifests retain defaults.
local P = {}
local function allowed(cp)
    return (cp >= 65 and cp <= 90) or (cp >= 97 and cp <= 122)
        or (cp >= 0x3400 and cp <= 0x4DBF) or (cp >= 0x4E00 and cp <= 0x9FFF)
        or (cp >= 0xF900 and cp <= 0xFAFF) or (cp >= 0x20000 and cp <= 0x2FA1F)
        or (cp >= 0x30000 and cp <= 0x323AF)
end
function P.label(value)
    assert(type(value) == "string", "button.text 必须为文字")
    local count = 0
    for _, cp in utf8.codes(value) do
        assert(allowed(cp), "按钮提示只接受英文字母或汉字")
        count = count + 1
    end
    assert(count >= 1 and count <= 3, "按钮提示必须为 1–3 个字母或汉字")
    return value
end
function P.default_label(name)
    local chars = {}
    pcall(function()
        for _, cp in utf8.codes(name or "") do
            if allowed(cp) then chars[#chars + 1] = utf8.char(cp) end
            if #chars == 3 then break end
        end
    end)
    return #chars > 0 and table.concat(chars) or "皮肤"
end
local function color(value)
    assert(type(value) == "string" and value:match("^#%x%x%x%x%x%x$"), "按钮颜色必须为 #RRGGBB")
    return value:upper()
end
function P.linear(value)
    local function channel(start)
        local v = tonumber(value:sub(start, start + 1), 16) / 255
        return v <= 0.04045 and v / 12.92 or ((v + 0.055) / 1.055) ^ 2.4
    end
    return {R = channel(2), G = channel(4), B = channel(6), A = 1}
end
function P.normalize(button, name)
    assert(button == nil or type(button) == "table", "button 必须为对象")
    button = button or {}
    local background = color(button.background_color or "#264A64")
    local c = P.linear(background)
    local automatic = (0.2126 * c.R + 0.7152 * c.G + 0.0722 * c.B) > 0.179 and "#101820" or "#FFFFFF"
    return {text = button.text and P.label(button.text) or P.default_label(name),
        background_color = background, text_color = color(button.text_color or automatic)}
end
return P
