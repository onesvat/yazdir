#import "common.typ": *
#show: setup.with(t("T6 · Monthly calendar", "T6 · Aylık takvim"))

#for (i, (year, month)) in ((2026, 11), (2026, 12), (2027, 1), (2027, 2)).enumerate() {
  if i > 0 { pagebreak() }
  text(28pt, weight: "bold")[#months.at(month - 1)]
  h(3mm)
  text(28pt, fill: luma(140))[#year]
  v(1mm)
  month-grid(year, month, cell: 30mm, size: 11pt, holiday-names: true)
  v(5mm)
  text(weight: "bold")[#t("Notes", "Notlar")]
  lines(5)
}
