#import "common.typ": *
#show: setup.with(t("T4 · Lists (A5)", "T4 · Listeler (A5)"), paper: "a5", margin: 10mm, size: 9.5pt)

#let section(name, count) = { text(weight: "bold")[#name]; checklist(count, gap: 6.8mm); v(4mm) }
#let dated(title) = heading-bar(title, extra: [#t("Date", "Tarih"): #field(30mm)])
#for i in range(4) {
  if i > 0 { pagebreak() }
  dated(t("Shopping list", "Alışveriş listesi"))
  v(3mm)
  grid(columns: (1fr, 1fr), gutter: 7mm,
    { section(t("Fruit & vegetables", "Manav"), 8); section(t("Meat · Fish", "Et · Tavuk · Balık"), 5); section(t("Dairy", "Süt ürünleri"), 6) },
    { section(t("Pantry", "Temel gıda · Kuru gıda"), 8); section(t("Household · Personal care", "Temizlik · Kişisel bakım"), 5); section(t("Other", "Diğer"), 6) })
}
#for i in range(4) {
  pagebreak()
  dated(t("To do", "Yapılacaklar"))
  v(3mm)
  text(weight: "bold")[#t("Must do today", "Bugün mutlaka")]
  checklist(4, gap: 7mm)
  v(5mm)
  text(weight: "bold")[#t("Other tasks", "Diğer işler")]
  checklist(14, gap: 7mm)
  v(5mm)
  text(weight: "bold")[#t("Notes", "Notlar")]
  lines(3, gap: 7mm)
}
