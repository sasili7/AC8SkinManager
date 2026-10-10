-- Four-column native UMG button grid; extra rows scroll vertically.
-- Slate latches toggle-button state, including clicks between Lua polls.
local P = require("presentation")
local Menu = {}
Menu.__index = Menu
local function valid(object)
    local ok, result = pcall(function() return object and object:IsValid() end)
    return ok and result
end
local function make(class, outer)
    local cls = StaticFindObject("/Script/UMG." .. class)
    assert(valid(cls), "缺少 UMG 类：" .. class)
    local object = StaticConstructObject(cls, outer)
    assert(valid(object), "无法创建控件：" .. class)
    return object
end
local function text(tree, value, size, color)
    local block = make("TextBlock", tree)
    block:SetText(FText(value))
    block:SetColorAndOpacity({SpecifiedColor = P.linear(color or "#E9F1F7"), ColorUseRule = 0})
    local font = block.Font
    font.Size = size
    block:SetFont(font)
    return block
end
local function margin(n) return {Left = n, Top = n, Right = n, Bottom = n} end
-- SlateEnums.h: Fill=0, Left/Top=1, Center=2, Right/Bottom=3.
local FILL, CENTER = 0, 2
-- Reuse the existing section heading's full Slate font, including its game font asset.
-- Discovery happens only when building our panel, never during the click poll.
local function match_heading_style(tree, heading)
    local ok, blocks = pcall(FindAllOf, "TextBlock")
    if not ok then return end
    local best, rank = nil, 0
    for _, block in ipairs(blocks or {}) do
        pcall(function()
            if not valid(block) or not block:IsVisible() then return end
            local raw = block:GetText():ToString()
            local value = raw:upper():gsub("[%[%]]", ""):gsub("%s+", " ")
            local score = value == "WEAPONS AMMO" and 3 or value == "PARTS" and 2
                or value == "AIRCRAFT SPECIFICATIONS" and 1
                or (value ~= "LIVERY" and raw:match("^%[.+%]$") and 0.5) or 0
            if score <= rank then return end
            local current = block
            for _ = 1, 16 do
                if not valid(current) then break end
                if current:GetFullName() == tree:GetFullName() then
                    best, rank = block, score; break
                end
                current = current:GetOuter()
            end
        end)
    end
    if best then
        pcall(function()
            heading:SetFont(best.Font)
            heading:SetColorAndOpacity(best.ColorAndOpacity)
        end)
    end
end
function Menu.new(on_click) return setmetatable({on_click = on_click, buttons = {}}, Menu) end
function Menu:hide()
    if valid(self.panel) then pcall(function() self.panel:RemoveFromParent() end) end
    self.panel, self.owner, self.scroll, self.geometry_key = nil, nil, nil, nil
    self.buttons = {}
end
function Menu:render(core, ctx)
    if not ctx then self:hide(); return false, "未找到选机界面" end
    local ui_key = ctx.ui_fingerprint or ctx.fingerprint
    local canvas_width, canvas_height = 0, 0
    pcall(function()
        local lib = StaticFindObject("/Script/UMG.Default__SlateBlueprintLibrary")
        local size = lib:GetLocalSize(ctx.widget.WidgetTree.RootWidget:GetCachedGeometry())
        canvas_width, canvas_height = math.floor(size.X + 0.5), math.floor(size.Y + 0.5)
    end)
    local geometry_key = tostring(canvas_width) .. "x" .. tostring(canvas_height)
    self.interactive = ctx.interactive ~= false
    local attached = valid(self.panel)
    if attached then
        local ok, parent = pcall(function() return self.panel:GetParent() end)
        -- Native page refreshes may remove our still-valid panel from its
        -- canvas. Validity alone does not establish that it is on screen.
        if ok then attached = valid(parent) and parent:GetFullName() == ctx.widget.WidgetTree.RootWidget:GetFullName() end
    end
    if self.owner ~= ui_key or not attached or self.geometry_key ~= geometry_key then
        self:hide()
        local ok, err = pcall(function()
            local tree, rows = ctx.widget.WidgetTree, core:rows()
            assert(valid(tree), "界面没有 WidgetTree")
            local root = tree.RootWidget
            assert(valid(root) and root:IsA(StaticFindObject("/Script/UMG.CanvasPanel")), "按钮挂载点待确认，请按 F7")
            local panel = make("VerticalBox", tree)
            self.panel = panel
            local heading = text(tree, "[LIVERY]", 16)
            match_heading_style(tree, heading)
            panel:AddChildToVerticalBox(heading)
            -- AC8 uses a larger logical canvas than the final screen. Fixed
            -- 12/16-point labels therefore appeared much smaller than native UI.
            local native_size = 16
            pcall(function() native_size = math.max(16, tonumber(heading.Font.Size) or 16) end)
            local width = 308 * native_size / 16
            if canvas_width > 0 then width = canvas_width * 0.16 end
            local button_width = math.max(native_size * 3.1, (width - 8) / 4 - 4)
            local font_size = math.ceil(native_size * 0.95)
            local button_height = math.ceil(native_size * 2.1)
            self.layout = {font_size = font_size, button_height = button_height, button_width = button_width}
            local scroll = make("ScrollBox", tree)
            self.scroll = scroll
            scroll:SetOrientation(1) -- Orient_Vertical
            scroll:SetScrollBarVisibility(0)
            scroll:SetScrollbarThickness({X = 4, Y = 4})
            local viewport = make("SizeBox", tree)
            viewport:SetHeightOverride(2 * (button_height + 4))
            viewport:SetContent(scroll)
            panel:AddChildToVerticalBox(viewport)
            local grid = make("UniformGridPanel", tree)
            grid:SetSlotPadding(margin(2))
            scroll:AddChild(grid)
            for index, row in ipairs(rows) do
                local presentation = row.button or P.normalize(row.id == "original" and
                    {text = "STD", background_color = "#687785"} or nil, row.name)
                local size = make("SizeBox", tree)
                size:SetWidthOverride(button_width); size:SetHeightOverride(button_height)
                local outline = make("Border", tree)
                outline:SetHorizontalAlignment(FILL); outline:SetVerticalAlignment(FILL)
                outline:SetPadding(margin(math.max(1, native_size / 16))); size:SetContent(outline)
                local layers = make("Overlay", tree)
                outline:SetContent(layers)
                local fill = make("Border", tree)
                fill:SetHorizontalAlignment(FILL); fill:SetVerticalAlignment(CENTER)
                fill:SetPadding({Left = 3, Top = 1, Right = 3, Bottom = 1})
                local tint = P.linear(presentation.background_color)
                tint.A = 0.78
                fill:SetBrushColor(tint)
                local art_slot = layers:AddChildToOverlay(fill)
                art_slot:SetHorizontalAlignment(FILL); art_slot:SetVerticalAlignment(FILL)
                local button = make("CheckBox", tree)
                button.HorizontalAlignment = FILL
                local style = button.WidgetStyle
                style.CheckBoxType = 1 -- ESlateCheckBoxType::ToggleButton
                style.Padding = margin(0)
                -- WidgetStyle is a reflected struct. Its fields are written before
                -- the control is attached and Slate builds it. SetWidgetStyle is
                -- a C++-only method in this game and cannot be called from Lua.
                button:SetIsChecked(false)
                -- Keep Slate's reliable click latch, hide its native checkbox
                -- decoration, and draw the flat colored rectangle separately.
                button:SetRenderOpacity(0)
                local hit_area = make("SizeBox", tree)
                hit_area:SetWidthOverride(button_width); hit_area:SetHeightOverride(button_height)
                button:SetContent(hit_area)
                local hit_slot = layers:AddChildToOverlay(button)
                hit_slot:SetHorizontalAlignment(FILL); hit_slot:SetVerticalAlignment(FILL)
                local label = text(tree, presentation.text, font_size, presentation.text_color)
                pcall(function()
                    label:SetFont(heading.Font)
                    local font = label.Font; font.Size = font_size; label:SetFont(font)
                end)
                label:SetJustification(1)
                fill:SetContent(label)
                local cell = grid:AddChildToUniformGrid(size, math.floor((index - 1) / 4), (index - 1) % 4)
                cell:SetHorizontalAlignment(FILL); cell:SetVerticalAlignment(FILL)
                self.buttons[#self.buttons + 1] = {control = button, outline = outline, fill = fill, index = index, id = row.id,
                    color = presentation.background_color}
            end
            -- Reserve four columns even when only one or two skins exist.
            if #rows < 4 then
                local spacer = make("SizeBox", tree)
                spacer:SetWidthOverride(button_width); spacer:SetHeightOverride(button_height)
                grid:AddChildToUniformGrid(spacer, 0, 3)
            end
            local slot = root:AddChildToCanvas(panel)
            slot:SetAnchors({Minimum = {X = 0.755, Y = 0.58}, Maximum = {X = 0.915, Y = 0.70}})
            slot:SetOffsets(margin(0))
            slot:SetZOrder(9999)
            self.owner = ui_key
            self.geometry_key = geometry_key
        end)
        if not ok then self:hide(); return false, tostring(err) end
    end
    return self:refresh(core)
end
function Menu:refresh(core)
    if not valid(self.panel) then return false, "按钮面板不可用" end
    local ok, err = pcall(function()
        for _, item in ipairs(self.buttons) do
            item.control:SetIsEnabled(self.interactive)
            if not self.interactive then item.control:SetIsChecked(false) end
            local selected = (core.applied_skin or "original") == item.id
            local edge = P.linear(selected and "#FFFFFF" or item.color)
            edge.A = selected and 1 or 0.5
            item.outline:SetBrushColor(edge)
            local fill = P.linear(item.color)
            if selected then
                fill.R = math.min(1, fill.R * 1.2 + 0.05)
                fill.G = math.min(1, fill.G * 1.2 + 0.05)
                fill.B = math.min(1, fill.B * 1.2 + 0.05)
            end
            fill.A = selected and 1 or 0.78
            item.fill:SetBrushColor(fill)
        end
    end)
    return ok, err
end
function Menu:poll()
    if not valid(self.panel) or self.interactive == false then return end
    for _, item in ipairs(self.buttons) do
        local ok, checked = pcall(function() return item.control:IsChecked() end)
        if ok and checked then
            item.control:SetIsChecked(false)
            if self.on_click then self.on_click(item.index, self.owner) end
            return
        end
    end
end
return Menu
