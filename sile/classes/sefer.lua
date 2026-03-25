--- Sefer document class for Hebrew book layout (Shefa Shlomo style).
--
-- Page zones:
--   headerframe  — running head (page num, book name, section, author)
--   mainzone     — primary lesson text (bold, ~12.5pt)
--   divider      — ornamental diamond row
--   makor_col    — right column: מקור השפע (sources)
--   tzinor_col   — left column: צינור השפע (stories)
--   *_overflow   — full-width continuation for L-shape
--
-- Frame definitions are set per-page via \pagetemplate in the .sil file.
-- This class provides the text styling commands only.
--
-- @use classes.sefer

local plain = require("classes.plain")
local class = pl.class(plain)
class._name = "sefer"

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

  -- ═══════════════════════════════════════
  -- MAIN TEXT — large bold Hebrew (top zone)
  -- ═══════════════════════════════════════
  self:registerCommand("maintext", function (_, content)
    SILE.call("font", {
      family = "Noto Serif Hebrew",
      size = "12.5pt",
      weight = 700,
      language = "he",
    })
    SILE.settings:temporarily(function ()
      SILE.settings:set("document.baselineskip", SILE.types.node.vglue("21pt"))
      SILE.settings:set("typesetter.parfillskip", SILE.types.node.glue())
      SILE.process(content)
      SILE.call("par")
    end)
  end)

  -- ═══════════════════════════════════════
  -- SECTION HEADER — centered, lighter
  -- ═══════════════════════════════════════
  self:registerCommand("sectionheader", function (_, content)
    SILE.call("smallskip")
    SILE.settings:temporarily(function ()
      SILE.call("font", {
        family = "Noto Serif Hebrew",
        size = "9.5pt",
        weight = 400,
        language = "he",
      })
      SILE.call("center", {}, content)
    end)
    SILE.call("smallskip")
  end)

  -- ═══════════════════════════════════════
  -- SECTION BODY — bold, same as main text
  -- ═══════════════════════════════════════
  self:registerCommand("sectionbody", function (_, content)
    SILE.call("font", {
      family = "Noto Serif Hebrew",
      size = "12.5pt",
      weight = 700,
      language = "he",
    })
    SILE.settings:temporarily(function ()
      SILE.settings:set("document.baselineskip", SILE.types.node.vglue("21pt"))
      SILE.settings:set("typesetter.parfillskip", SILE.types.node.glue())
      SILE.process(content)
      SILE.call("par")
    end)
  end)

  -- ═══════════════════════════════════════
  -- SOURCE TEXT — small regular (bottom columns)
  -- ═══════════════════════════════════════
  self:registerCommand("sourcetext", function (_, content)
    SILE.call("font", {
      family = "Noto Serif Hebrew",
      size = "8.5pt",
      weight = 400,
      language = "he",
    })
    SILE.settings:temporarily(function ()
      SILE.settings:set("document.baselineskip", SILE.types.node.vglue("12pt"))
      SILE.process(content)
      SILE.call("par")
    end)
  end)

  -- ═══════════════════════════════════════
  -- DIVIDER — decorative diamond row
  -- ═══════════════════════════════════════
  self:registerCommand("sefer-divider", function (_, _)
    SILE.call("smallskip")
    SILE.settings:temporarily(function ()
      SILE.call("font", { family = "Noto Serif Hebrew", size = "3.5pt" })
      SILE.call("center", {}, function ()
        SILE.typesetter:typeset("◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆  ◆")
      end)
    end)
    SILE.call("medskip")
  end)

  -- ═══════════════════════════════════════
  -- COLUMN TITLE — bold with fleuron ornaments
  -- ═══════════════════════════════════════
  self:registerCommand("col-title", function (_, content)
    SILE.settings:temporarily(function ()
      SILE.call("font", {
        family = "Noto Serif Hebrew",
        size = "9.5pt",
        weight = 700,
        language = "he",
      })
      SILE.call("center", {}, function ()
        SILE.typesetter:typeset("❧ ")
        SILE.process(content)
        SILE.typesetter:typeset(" ❧")
      end)
    end)
    SILE.call("medskip")
  end)

  -- ═══════════════════════════════════════
  -- RUNNING HEADER
  -- ═══════════════════════════════════════
  self:registerCommand("sefer-header", function (options, _)
    SILE.settings:temporarily(function ()
      SILE.call("font", {
        family = "Noto Serif Hebrew",
        weight = 700,
        language = "he",
      })
      -- Page number (rightmost in RTL)
      SILE.call("font", { size = "12pt" })
      SILE.typesetter:typeset(options.pagenum or "")
      SILE.call("hfill")
      -- Book name (large center)
      SILE.call("font", { size = "17pt" })
      SILE.typesetter:typeset(options.bookname or "שפע")
      SILE.call("quad")
      -- Section name
      SILE.call("font", { size = "12pt" })
      SILE.typesetter:typeset(options.section or "")
      SILE.call("hfill")
      -- Author name (leftmost in RTL)
      SILE.call("font", { size = "13pt" })
      SILE.typesetter:typeset(options.author or "שלמה")
    end)
    SILE.call("par")
    SILE.call("bigskip")
  end)
end

return class
