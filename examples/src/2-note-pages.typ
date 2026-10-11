#import "common.typ": *
#show: setup.with(t("T2 · Note pages", "T2 · Not sayfaları"))

#let top = {
  grid(columns: (1fr, 45mm), gutter: 6mm,
    [#t("Topic", "Konu"): #field(1fr)],
    [#t("Date", "Tarih"): #field(1fr)])
  v(4mm)
}
#let ruled = layout(b => for y in range(0, int(b.height / 8mm) + 1) { place(dy: y * 8mm, line(length: 100%, stroke: 0.4pt + light)) })
#let squared = layout(b => {
  for y in range(0, int(b.height / 5mm) + 1) { place(dy: y * 5mm, line(length: 100%, stroke: 0.3pt + light)) }
  for x in range(0, int(b.width / 5mm) + 1) { place(dx: x * 5mm, line(angle: 90deg, length: b.height, stroke: 0.3pt + light)) }
})
#let dotted = layout(b => {
  for y in range(0, int(b.height / 5mm) + 1) { for x in range(0, int(b.width / 5mm) + 1) {
    place(dx: x * 5mm - 0.3mm, dy: y * 5mm - 0.3mm, circle(radius: 0.3mm, fill: grey, stroke: none))
  } }
})
#let cornell = grid(columns: (55mm, 1fr), rows: (1fr, 45mm), stroke: (x, y) => (
    right: if x == 0 and y == 0 { 0.6pt + grey }, top: if y == 1 { 0.6pt + grey }),
  inset: 3mm,
  text(8pt, fill: luma(110))[#t("Cues / questions", "Anahtar kelimeler / sorular")], text(8pt, fill: luma(110))[#t("Notes", "Notlar")],
  grid.cell(colspan: 2, text(8pt, fill: luma(110))[#t("Summary", "Özet")]))

#let sheets = (
  (t("Ruled", "Çizgili"), ruled), (t("Squared (5 mm)", "Kareli (5 mm)"), squared), (t("Dot grid (5 mm)", "Noktalı (5 mm)"), dotted),
  (t("Cornell notes", "Cornell not sayfası"), cornell), (t("Ruled", "Çizgili"), ruled),
)
#for (i, (name, art)) in sheets.enumerate() {
  if i > 0 { pagebreak() }
  text(8pt, fill: luma(130))[#name]
  v(1mm)
  top
  block(width: 100%, height: 1fr, art)
}
