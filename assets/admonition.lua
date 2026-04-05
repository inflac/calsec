local function make_box(type, icon, title, content)
  return pandoc.RawBlock("html",
    '<div class="admonition ' .. type .. '">' ..
    '<div class="admonition-title">' ..
    icon .. ' ' .. title ..
    '</div>' ..
    '<div class="admonition-content">' ..
    content ..
    '</div>' ..
    '</div>'
  )
end

-- Handle blockquotes so they don't wrap admonitions
function BlockQuote(el)
  return el.content
end

function Para(el)
  local text = pandoc.utils.stringify(el)

  local type, content = text:match("^%[!(%w+)%]%s*(.*)")

  if type and content then
    type = type:upper()

    if type == "WARNING" then
      return make_box("warning", "⚠️", "WARNING", content)
    elseif type == "NOTE" then
      return make_box("note", "ℹ️", "NOTE", content)
    elseif type == "TIP" then
      return make_box("tip", "💡", "TIP", content)
    elseif type == "IMPORTANT" then
      return make_box("important", "❗", "IMPORTANT", content)
    end
  end
end