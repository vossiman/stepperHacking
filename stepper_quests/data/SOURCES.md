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

## Waypoints added 2026-11-17

Added so that no gap between consecutive waypoints is longer than 3.0
walkable miles. Each sits between its neighbours' `road_miles`, takes the
mode of the waypoint that ends its gap, and paraphrases the chapter named
below. Where the book gives few events (the days on the Anduin, the long
foot stretches after Weathertop), the entry describes country or travel the
chapter itself mentions.

- `through-the-dark-fields`: Three is Company
- `packs-on-again`: Three is Company
- `the-road-climbs`: Three is Company
- `no-path-under-the-trees`: A Knife in the Dark
- `single-file`: A Knife in the Dark
- `lonely-country`: A Knife in the Dark
- `strider-names-weathertop`: A Knife in the Dark
- `going-slowly`: Flight to the Ford
- `heavy-packs`: Flight to the Ford
- `the-valley-floor`: Flight to the Ford
- `clear-of-the-road`: Flight to the Ford
- `grey-slopes`: Flight to the Ford
- `grey-afternoon`: Flight to the Ford
- `steepening-slopes`: Flight to the Ford
- `frodo-grows-quiet`: Flight to the Ford
- `land-falling-east`: Flight to the Ford
- `looking-for-cover`: Flight to the Ford
- `marching-at-dusk`: The Ring Goes South
- `gullies-in-the-dark`: The Ring Goes South
- `the-long-way-down`: A Journey in the Dark
- `below-the-snow`: A Journey in the Dark
- `a-halt-to-decide`: A Journey in the Dark
- `boromir-objects`: A Journey in the Dark
- `frodo-asks-to-wait`: A Journey in the Dark
- `dusk-on-the-hillside`: A Journey in the Dark
- `wargs-west-of-the-mountains`: A Journey in the Dark
- `gimlis-grief`: Farewell to Lorien
- `the-swift-grey-river`: Farewell to Lorien
- `grey-woods-on-the-banks`: The Great River
- `drifting-with-the-stream`: The Great River
- `black-swans`: The Great River
- `forests-of-reeds`: The Great River
- `wide-and-mournful`: The Great River
- `the-withered-east-bank`: The Great River
- `birds-in-the-reeds`: The Great River
- `the-last-southern-mountains`: The Great River
- `paddling-hard`: The Great River
- `chill-air-from-the-east`: The Great River
- `boromir-restless`: The Great River
- `the-dark-river`: The Great River
- `downs-of-withered-grass`: The Great River
- `a-new-moon`: The Great River
- `bleak-wolds`: The Great River
- `stony-banks`: The Great River
- `grey-hills-ahead`: The Great River
- `steepening-banks`: The Great River
- `among-the-hills`: The Great River
- `rapids-somewhere-below`: The Great River
- `below-the-rapids`: The Great River
- `tol-brandir`: The Great River
- `sheer-drops`: The Taming of Smeagol
- `gollum-slinks-back`: The Passage of the Marshes
- `sinking-walls`: The Passage of the Marshes
- `in-the-shadows`: Of Herbs and Stewed Rabbit
- `mounds-of-slag`: Of Herbs and Stewed Rabbit
- `blind-dark`: Shelob's Lair
- `sams-new-strength`: Mount Doom
