#import "common.typ": *
#show: setup.with(t("T3 · Pocket planner (booklet)", "T3 · Cep ajandası (kitapçık)"), paper: "a5", margin: 10mm, size: 9pt)

#align(center + horizon, {
  text(30pt, weight: "bold")[#t("Pocket Planner", "Cep Ajandası")]
  v(2mm)
  text(14pt, fill: luma(90))[#months.at(10) 2026 – #months.at(9) 2027]
  v(18mm)
  line(length: 50%, stroke: 0.6pt + grey)
  v(4mm)
  text(10pt, fill: luma(110))[#t("Name", "Ad"): #field(55mm)]
})
#for i in range(6) {
  pagebreak()
  for j in range(2) {
    let month = calc.rem(10 + i * 2 + j, 12) + 1
    let year = if month >= 11 { 2026 } else { 2027 }
    text(13pt, weight: "bold")[#months.at(month - 1) #year]
    v(-1mm)
    month-grid(year, month, cell: 11.5mm, size: 8pt)
    if j == 0 { v(5mm) }
  }
}
#pagebreak()
#if lang == "tr" {
  text(13pt, weight: "bold")[Sabit tarihli resmî tatiller]
  v(1mm)
  for h in holidays [
    #grid(columns: (22mm, 1fr), [*#h.at(1) #months.at(h.at(0) - 1)*], h.at(2))
    #v(-1mm)
  ]
  text(7.5pt, fill: luma(110))[Dinî bayramların tarihleri her yıl değişir; resmî takvimden ekleyin.]
} else {
  text(13pt, weight: "bold")[Important dates]
  v(1mm)
  for _ in range(7) {
    grid(columns: (22mm, 1fr), gutter: 3mm, field(100%), field(100%))
    v(2.5mm)
  }
}
#v(4mm)
#text(13pt, weight: "bold")[#t("Notes", "Notlar")]
#lines(12, gap: 7mm)
