#import "common.typ": *
#show: setup.with(t("T1 · Weekly planner", "T1 · Haftalık planlayıcı"))

#let monday = datetime(year: 2026, month: 10, day: 12)
#for week in range(4) {
  let start = monday + duration(weeks: week)
  let end = start + duration(days: 6)
  let span = if start.month() == end.month() [#start.day() – #end.day() #months.at(end.month() - 1) #end.year()] else [#start.day() #months.at(start.month() - 1) – #end.day() #months.at(end.month() - 1) #end.year()]
  if week > 0 { pagebreak() }
  heading-bar(t("Weekly plan", "Haftalık plan"), extra: span)
  v(3mm)
  grid(
    columns: (1.55fr, 1fr),
    gutter: 6mm,
    {
      for i in range(7) {
        let d = start + duration(days: i)
        let hol = holiday(d.month(), d.day())
        block(height: 34.5mm, width: 100%, stroke: (top: 0.6pt + grey), inset: (top: 2mm), below: 0pt, {
          text(weight: "bold")[#days.at(i)]
          h(2mm)
          text(fill: luma(110))[#date-in(d)]
          if hol != none { h(2mm); text(8pt, weight: "bold")[· #hol.at(2)] }
          lines(3, gap: 7.5mm)
        })
      }
    },
    {
      text(weight: "bold")[#t("Top 3 priorities", "Bu haftanın 3 önceliği")]
      for i in range(1, 4) { block(height: 9mm, below: 0pt, align(bottom, grid(columns: (5mm, 1fr), [#i.], line(length: 100%, stroke: 0.4pt + light)))) }
      v(6mm)
      text(weight: "bold")[#t("To do", "Yapılacaklar")]
      checklist(12)
      v(6mm)
      text(weight: "bold")[#t("Notes", "Notlar")]
      lines(9)
    },
  )
}
