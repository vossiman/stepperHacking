# Sources for frodo.json

All retrieved on 2026-10-29.

## Mileage (primary)

Karen Wynn Fonstad's day-by-day "Pathway Mileage and Descriptions" tables,
written for the Eowyn Challenge site (home.insightbb.com/~eowynchallenge, now
offline) and based on her *The Atlas of Middle-earth*. Read from Internet
Archive snapshots:

| Stage | Total | Snapshot |
|---|---|---|
| Bag End to Rivendell | 458 | https://web.archive.org/web/20040607234410/http://home.insightbb.com:80/~eowynchallenge/Tools/Bag_end/bag_end.html |
| Rivendell to Lothlorien | 462 | https://web.archive.org/web/20040702073118/http://home.insightbb.com:80/~eowynchallenge/Tools/Rivendell_Lorien/rivendell_lorien.html |
| Lothlorien to Rauros | 389 | https://web.archive.org/web/20040608013015/http://home.insightbb.com:80/~eowynchallenge/Tools/Lorien_Rauros/lorien_rauros.html |
| Rauros to Mount Doom (Frodo and Sam) | 470 | https://web.archive.org/web/20041031071003/http://home.insightbb.com:80/~eowynchallenge/Tools/Frodo_and_Sam/frodo_and_sam.html |

Snapshot list found with the Wayback CDX API:
http://web.archive.org/cdx/search/cdx?url=home.insightbb.com/~eowynchallenge/*

## Cross-checks

- https://under1000skies.org/eowyn/ (Eowyn Challenge mirror; confirms the
  original site is discontinued and that its tables come from Fonstad)
- https://under1000skies.org/eowyn/bag-end-to-rivendell-frodo/ (confirms the
  458 mile, 28 day Bag End to Rivendell stage)

## How the file was built

- `road_miles` is cumulative from Bag End. Stage offsets: Rivendell 458,
  Caras Galadhon 920, Parth Galen 1309, Crack of Doom 1779.
- Waypoints at the table's mile marks use the table's mileage directly.
- Where the table gives only a day's end (for example 15 mile night marches
  south of Rivendell), extra waypoints naming events and features from the
  books are spaced evenly between the table's marks, rounded to half a mile.
- On the boat and horse stretches, events from the books (such as nights on
  the river and Gollum following on a log) are added between named places so
  that no gap is longer than 10 walkable miles (40 road miles by boat).
- The table's "bonus miles" (Gollum's visit to Shelob, Sam's trips inside the
  Tower, the escape from Mount Doom and the eagles) are not part of the road.
- Modes: the gallop on Asfaloth from the red-stone cutting to the Ford is
  `horse`; Lorien to Parth Galen and the crossing of Nen Hithoel are
  `boat`, except the walk to the Silverlode lawn and the portage round Sarn
  Gebir, which are `foot`; Sam carrying Frodo on Mount Doom is `carried`;
  everything else is `foot`.
- Story text is original wording; Tolkien's chapter titles are used as given.
