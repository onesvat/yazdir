// Shared parts of the example / test set: the test header (↑ TOP ↑ + page number) and calendar helpers.
// Compile with:  typst compile --input lang=en file.typ   (or lang=tr)

#let lang = sys.inputs.at("lang", default: "en")
#let t(en, tr) = if lang == "tr" { tr } else { en }

#let months = t(
  ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
  ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"),
)
#let days = t(
  ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
  ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"),
)
#let days-short = t(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"), ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"))

// Fixed-date public holidays (Turkish edition only; religious holidays move every year).
#let holidays = if lang == "tr" {
  (
    (1, 1, "Yılbaşı"),
    (4, 23, "Ulusal Egemenlik ve Çocuk Bayramı"),
    (5, 1, "Emek ve Dayanışma Günü"),
    (5, 19, "Atatürk'ü Anma, Gençlik ve Spor Bayramı"),
    (7, 15, "Demokrasi ve Millî Birlik Günü"),
    (8, 30, "Zafer Bayramı"),
    (10, 29, "Cumhuriyet Bayramı"),
  )
} else { () }

#let grey = luma(150)
#let light = luma(205)

#let setup(code, paper: "a4", margin: 12mm, size: 10pt, body) = {
  set page(
    paper: paper,
    margin: (x: margin, top: margin + 7mm, bottom: margin),
    header-ascent: 35%,
    header: context {
      let n = counter(page).get().first()
      let total = counter(page).final().first()
      set text(7pt, fill: luma(120))
      grid(
        columns: (1fr, auto, 1fr),
        align: (left + horizon, center + horizon, right + horizon),
        [#code],
        text(8pt, weight: "bold", fill: black)[#t("↑ TOP ↑", "↑ ÜST ↑")],
        [#t("Page", "Sayfa") #text(11pt, weight: "bold", fill: black)[#n] / #total],
      )
    },
  )
  set text(font: ("Inter", "Cantarell", "Noto Sans"), lang: lang, size: size)
  body
}

#let days-in-month(year, month) = {
  let next = if month == 12 { datetime(year: year + 1, month: 1, day: 1) } else { datetime(year: year, month: month + 1, day: 1) }
  int((next - datetime(year: year, month: month, day: 1)).days())
}

#let holiday(month, day) = holidays.find(h => h.at(0) == month and h.at(1) == day)

#let month-grid(year, month, cell: 10mm, size: 8pt, holiday-names: false) = {
  let lead = datetime(year: year, month: month, day: 1).weekday() - 1
  let n = days-in-month(year, month)
  let cells = range(lead).map(_ => []) + range(1, n + 1).map(d => {
    let h = holiday(month, d)
    let weekend = calc.rem(lead + d - 1, 7) >= 5
    let strong-day = h != none or weekend
    [#text(size, weight: if strong-day { "bold" } else { "regular" }, fill: if strong-day { black } else { luma(60) })[#d]#if h != none {
        if holiday-names { linebreak(); text(size * 0.62, weight: "bold")[#h.at(2)] } else { text(size * 0.8)[\*] }
      }]
  })
  cells += range(calc.rem(7 - calc.rem(cells.len(), 7), 7)).map(_ => [])
  set text(size)
  grid(
    columns: (1fr,) * 7,
    rows: (auto,) + (cell,) * int(cells.len() / 7),
    stroke: 0.4pt + grey,
    inset: 3pt,
    align: left + top,
    ..days-short.map(d => align(center, text(weight: "bold")[#d])),
    ..cells,
  )
}

#let lines(count, gap: 8mm) = {
  for _ in range(count) {
    v(gap - 0.4pt, weak: true)
    line(length: 100%, stroke: 0.4pt + light)
  }
}

#let checkbox = box(width: 3.2mm, height: 3.2mm, stroke: 0.6pt + grey, baseline: 0.4mm)

#let checklist(count, gap: 8mm) = {
  for _ in range(count) {
    block(height: gap, below: 0pt, above: 0pt, align(bottom, grid(
      columns: (auto, 1fr),
      gutter: 2mm,
      checkbox, line(length: 100%, stroke: 0.4pt + light),
    )))
  }
}

#let field(width) = box(width: width, line(length: 100%, stroke: 0.5pt + grey))

#let heading-bar(title, extra: none) = {
  text(17pt, weight: "bold")[#title]
  if extra != none { h(3mm); text(10pt, fill: luma(110))[#extra] }
  v(-2mm)
  line(length: 100%, stroke: 1pt)
}

#let date-in(d) = t([#d.day() #months.at(d.month() - 1)], [#d.day() #months.at(d.month() - 1)])
