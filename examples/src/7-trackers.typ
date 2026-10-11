#import "common.typ": *
#show: setup.with(t("T7 · Trackers", "T7 · Takip sayfaları"), size: 9.5pt)

#heading-bar(t("Habit tracker", "Alışkanlık takibi"), extra: [#t("Month", "Ay"): #field(35mm)])
#v(4mm)
#set text(7pt)
#grid(
  columns: (38mm,) + (1fr,) * 31,
  rows: (6mm,) + (9mm,) * 14,
  stroke: 0.4pt + grey,
  align: center + horizon,
  [*#t("Habit", "Alışkanlık")*], ..range(1, 32).map(d => [#d]),
  ..range(14 * 32).map(_ => []),
)
#set text(9.5pt)
#v(6mm)
#text(weight: "bold")[#t("End-of-month review", "Ay sonu değerlendirmesi")]
#lines(8)

#pagebreak()
#heading-bar(t("Reading list", "Okuma listesi"))
#v(3mm)
#grid(
  columns: (8mm, 1fr, 45mm, 22mm, 18mm),
  rows: (7mm,) + (9.8mm,) * 24,
  stroke: (x, y) => (bottom: 0.4pt + light, top: if y == 0 { 0.8pt }),
  align: left + horizon,
  inset: (x: 1.5mm),
  [*\#*], [*#t("Book", "Kitap")*], [*#t("Author", "Yazar")*], [*#t("Finished", "Bitiş")*], [*#t("Rating", "Puan")*],
  ..range(24).map(i => ([#(i + 1)], [], [], [], [☆☆☆☆☆])).flatten(),
)

#pagebreak()
#heading-bar(t("Goals for 2027", "2027 hedefleri"))
#v(3mm)
#grid(columns: (1fr, 1fr), gutter: 8mm, row-gutter: 6mm,
  ..(t("Health", "Sağlık"), t("Work · Career", "İş · Kariyer"), t("Money", "Para"), t("Learning", "Öğrenme"),
     t("Relationships", "İlişkiler"), t("Home", "Ev · Düzen")).map(name => {
    text(12pt, weight: "bold")[#name]
    checklist(6)
  }))
#v(4mm)
#text(12pt, weight: "bold")[#t("Word of the year:", "Yılın tek kelimesi:")] #field(60mm)
