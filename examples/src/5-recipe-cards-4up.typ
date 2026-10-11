#import "common.typ": *
#show: setup.with(t("T5 · Recipe card", "T5 · Tarif kartı"), paper: "a6", margin: 7mm, size: 7.5pt)

#let labelled(name) = [#text(fill: luma(110))[#name] #box(width: 1fr, line(length: 100%, stroke: 0.4pt + grey))]
#for i in range(16) {
  if i > 0 { pagebreak() }
  text(12pt, weight: "bold")[#t("Recipe", "Tarif")]
  h(1fr)
  for _ in range(5) { text(10pt, fill: grey)[☆] }
  v(-2mm)
  line(length: 100%, stroke: 0.8pt)
  labelled(t("Name:", "Adı:"))
  v(1mm)
  grid(columns: (1fr, 1fr, 1fr), gutter: 3mm, labelled(t("Serves:", "Kişi:")), labelled(t("Prep:", "Hazırlık:")), labelled(t("Cook:", "Pişirme:")))
  v(1mm)
  grid(columns: (1fr, 1.4fr), gutter: 4mm,
    { text(weight: "bold")[#t("Ingredients", "Malzemeler")]; checklist(15, gap: 6.2mm) },
    { text(weight: "bold")[#t("Method", "Yapılışı")]; lines(15, gap: 6.2mm) })
}
