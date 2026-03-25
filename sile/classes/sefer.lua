--- Sefer document class for Hebrew book layout (Shefa Shlomo style)
-- L-shape dual columns using SILE's frame system
-- @use classes.sefer

local plain = require("classes.plain")
local class = pl.class(plain)
class._name = "sefer"

-- Default frameset — these are the base frames.
-- Per-page, Python generates dynamic pagetemplate overrides with
-- specific frame dimensions for the L-shape.
class.defaultFrameset = {
  content = {
    left = "12mm",
    right = "100%pw - 14mm",
    top = "22mm",
    bottom = "100%ph - 9mm",
  },
  folio = {
    left = "left(content)",
    right = "right(content)",
    height = "0",
    bottom = "100%ph - 5mm",
  },
}

function class:_init (options)
  plain._init(self, options)
  self:loadPackage("frametricks")
end

function class:registerCommands ()
  plain.registerCommands(self)

  -- ═══ Main text: large bold Hebrew ═══
  self:registerCommand("maintext", function (_, content)
    SILE.call("font", {
      family = "Noto Serif Hebrew",
      size = "12.5pt",
      weight = 700,
      language = "he",
    })
    SILE.settings:temporarily(function ()
      SILE.settings:set("document.baselineskip", SILE.types.node.vglue("21pt"))
      SILE.process(content)
      SILE.call("par")
    end)
  end)

  -- ═══ Section header ═══
  self:registerCommand("sectionheader", function (_, content)
    SILE.call("smallskip")
    SILE.call("font", {
      family = "Noto Serif Hebrew", size = "9.5pt", weight = 400, language = "he",
    })
    SILE.call("center", {}, content)
    SILE.call("smallskip")
  end)

  -- ═══ Section body ═══
  self:registerCommand("sectionbody", function (_, content)
    SILE.call("font", {
      family = "Noto Serif Hebrew", size = "12.5pt", weight = 700, language = "he",
    })
    SILE.settings:temporarily(function ()
      SILE.settings:set("document.baselineskip", SILE.types.node.vglue("21pt"))
      SILE.process(content)
      SILE.call("par")
    end)
  end)

  -- ═══ Source text (small, for bottom columns) ═══
  self:registerCommand("sourcetext", function (_, content)
    SILE.call("font", {
      family = "Noto Serif Hebrew", size = "8.5pt", weight = 400, language = "he",
    })
    SILE.settings:temporarily(function ()
      SILE.settings:set("document.baselineskip", SILE.types.node.vglue("12.5pt"))
      SILE.process(content)
      SILE.call("par")
    end)
  end)

  -- ═══ Divider ═══
  self:registerCommand("sefer-divider", function (_, _)
    SILE.call("font", { family = "Noto Serif Hebrew", size = "4pt" })
    SILE.call("center", {}, function ()
      SILE.typesetter:typeset("◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆")
    end)
    SILE.call("medskip")
  end)

  -- ═══ Column header ═══
  self:registerCommand("col-title", function (_, content)
    SILE.call("font", {
      family = "Noto Serif Hebrew", size = "9.5pt", weight = 700, language = "he",
    })
    SILE.call("center", {}, function ()
      SILE.typesetter:typeset("❧ ")
      SILE.process(content)
      SILE.typesetter:typeset(" ❧")
    end)
    SILE.call("medskip")
  end)

  -- ═══ Running header ═══
  self:registerCommand("sefer-header", function (options, _)
    SILE.call("font", { family = "Noto Serif Hebrew", weight = 700, language = "he" })
    SILE.call("font", { size = "12pt" })
    SILE.typesetter:typeset(options.pagenum or "")
    SILE.call("hfill")
    SILE.call("font", { size = "17pt" })
    SILE.typesetter:typeset(options.bookname or "שפע")
    SILE.call("quad")
    SILE.call("font", { size = "12pt" })
    SILE.typesetter:typeset(options.section or "")
    SILE.call("hfill")
    SILE.call("font", { size = "13pt" })
    SILE.typesetter:typeset(options.author or "שלמה")
    SILE.call("par")
    SILE.call("bigskip")
  end)
end

return class
