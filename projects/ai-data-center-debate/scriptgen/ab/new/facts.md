# Fact Sheet — AI Data Center Debate

Sources: [S1] Business Insider "Exposing The Dark Side…" (4,361w) · [S2] Matt Walsh "Here's What Nobody's Telling You…" (7,883w) · [S3] short explainer "How data centers work…" (242w) · [S4] "We Saw What AI Data Centers Don't Want You to See" (3,485w) · [S5] "What's Inside an AI Data Center?" (2,425w)

Tag format: `- <fact> — src:[..] · purpose:.. · beat:.. · conf:.. · role:..`

---

## Beat: HOOK (a concrete, stopping fact)

- Because a utility decided data centers were more lucrative, ~49,000–50,000 residents on the California side of Lake Tahoe were told their power supplier (NV Energy) will stop providing electricity after May 2027; regulators can't force it to keep serving them — src:[S2] · purpose:hook · beat:hook · conf:verified · role:supports
- Giant data-center warehouses are being built across the US at a rate of more than two every week — src:[S1,S2] · purpose:hook · beat:hook · conf:verified · role:supports
- A single large data center can consume more power than half a million homes — src:[S2] · purpose:hook · beat:hook · conf:claimed · role:supports
- These "cloud" machines don't live in the cloud; they live in buildings called data centers — src:[S5] · purpose:transition · beat:hook · conf:verified · role:context

## Beat: CONTEXT (what a data center is + the scale of the boom)

- A data center is essentially a factory for computation — rows of servers/GPUs, storage, power distribution, cooling, heavy security — src:[S5] · purpose:authority · beat:context · conf:verified · role:context
- One large data center uses the same amount of electricity as it takes to power 400,000 electric cars (IEA) — src:[S3] · purpose:proof · beat:context · conf:verified · role:context
- Asking ChatGPT to compose an answer takes ~10x the electricity of a traditional Google search (IEA); ~2.9 Wh per query vs ~0.3 Wh (per S5) — src:[S3,S5] · purpose:proof · beat:context · conf:verified · role:context
- Business Insider's permit-based map found 1,240 data centers built or approved by end of 2024 — nearly 4x the number in 2010 — src:[S1] · purpose:proof · beat:context · conf:verified · role:supports
- Amazon, Microsoft, Google and Meta collectively own about one-third of all data-center capacity — src:[S2] · purpose:proof · beat:context · conf:verified · role:context
- 177 of the mapped data centers belong to Amazon; biggest power users are Amazon, Microsoft, Google, Meta, QTS — src:[S1] · purpose:proof · beat:context · conf:verified · role:context
- DOE 2024 report: AI-driven demand could push data centers to as much as 12% of total US electricity use, up from just over 4% in 2023 — src:[S1,S5] · purpose:proof · beat:context · conf:verified · role:supports
- Stargate (OpenAI/Oracle/SoftBank), rural Texas: eventually 4 million sq ft across 1,100 acres — larger than Central Park — src:[S4,S5] · purpose:proof · beat:context · conf:verified · role:supports
- Big tech projected to spend >$800 billion on AI infrastructure in 2026, exceeding $1 trillion in 2027 — on par with the entire US defense budget — src:[S4] · purpose:proof · beat:context · conf:claimed · role:supports
- Loudoun County, Virginia is the world's largest data-center market ("data center alley"); as much as a third of the planet's internet traffic flows through Virginia — src:[S1,S5] · purpose:proof · beat:context · conf:verified · role:context

## Beat: EVIDENCE (who bears the costs — power bills, water, noise, homes)

### Power bills / grid
- In Virginia, Dominion Energy disclosed it would need to roughly double electricity generation by 2039 (mainly data centers + EVs), costing up to $103 billion and raising residential bills by as much as 50% — src:[S1] · purpose:proof · beat:evidence · conf:verified · role:supports
- 1,200+ tracked data centers combined could soon consume more power than Poland did in 2023; AI could use as much as 600 TWh by 2028 — src:[S1] · purpose:proof · beat:evidence · conf:verified · role:supports
- In Nebraska, one Meta campus in Springfield could use as much power in a year as 400,000 homes; a utility postponed closing two Omaha coal plants and in 2025 decided to build two new natural-gas plants — src:[S1] · purpose:proof · beat:evidence · conf:verified · role:supports
- Amazon, Microsoft, Google told Business Insider they're committed to paying their full share for grid upgrades — but there's evidence costs are already passed to customers — src:[S1] · purpose:contrast · beat:evidence · conf:verified · role:context

### Water
- Up to 43% of the largest data centers sit in areas of high or extremely high water stress; more than half of Microsoft's and nearly half of Amazon's are in high water-scarcity areas — src:[S1] · purpose:proof · beat:evidence · conf:verified · role:supports
- A Microsoft cluster in Maricopa County, AZ planned ~1 million gallons/day per building — 1.83 billion gallons/year, enough for ~61,000 people (a city the size of Santa Cruz) — in an area of extreme water stress drawing from the shrinking Colorado River (river flow down 20% since 2000) — src:[S1] · purpose:proof · beat:evidence · conf:verified · role:supports
- Newton County, GA is on track for a water deficit by 2030; Meta's data center uses ~10% of the county's daily water, and nine more companies applied, some asking up to 6 million gallons/day (NYT) — src:[S2] · purpose:proof · beat:evidence · conf:verified · role:supports
- Google's Council Bluffs (S5) and Midlothian, TX (S1, 160M gallons in 2023) sites consumed roughly a billion / hundreds of millions of gallons of water in a year — src:[S1,S5] · purpose:proof · beat:evidence · conf:verified · role:supports

### Noise / health / homes
- Carlos Janis in Manassas, VA measures data-center noise twice daily, spent $20,000 on insulation and windows; his 7-year-old began having nightmares — Amazon says its centers operate well below required sound levels — src:[S1] · purpose:humanize · beat:evidence · conf:verified · role:supports
- The American Public Health Association says chronic noise exposure can cause cardiovascular disease and increased stress — src:[S1] · purpose:authority · beat:evidence · conf:verified · role:supports
- Eminent domain: Ansley in Coweta County, GA is losing her childhood home to a Georgia Power transmission-line expansion for a data center; a Charlotte County, VA farmer (Todd Lax) was offered ~$1,500/acre (~$13,000) by Dominion; a dozen+ Kentucky farmers were threatened (Guardian) — src:[S2] · purpose:humanize · beat:evidence · conf:verified · role:supports
- Shell companies hide buyers to get land cheap: Google set up shell companies in at least five cities (Washington Post; e.g. "Jetstream LLC"); Business Insider found Google hiding behind "Magellan/Mellin Enterprises LLC" in Ohio via a trade-secret exemption — src:[S1,S2] · purpose:proof · beat:evidence · conf:verified · role:supports
- In Richland Parish, LA, Meta is building a ~$27 billion data center; rents jumped from ~$650 to ~$2,000–2,500/month and ~4,000 extra people moved into a parish of ~20,000 — src:[S2] · purpose:humanize · beat:evidence · conf:verified · role:supports

### The transparency / regulation gap
- There is no official public directory, map, or single regulator for US data centers; companies use NDAs, redacted records, and trade-secret exemptions to hide details — src:[S1,S4] · purpose:proof · beat:evidence · conf:verified · role:supports
- In Texas, Stargate got low-level "permit by rule" authorizations (the kind used for an autobody shop or dry cleaner) that require no public notice or input; ex-regulator Kathryn Guerra says the industry is expanding beyond the state's ability to regulate it (enforcement cases 10 years old) — src:[S4] · purpose:authority · beat:evidence · conf:verified · role:supports
- xAI's Colossus (South Haven, MS) ran gas turbines on trailers, calling them "temporary" to avoid permits — out of step with longstanding EPA policy — src:[S4] · purpose:proof · beat:evidence · conf:verified · role:supports

## Beat: TURN (the honest steelman — the boom really does deliver, and much fear is overblown)

- Loudoun County's budget says data centers generate ~38% of general-fund revenue — enough that the county actually cut property taxes for residents — src:[S5] · purpose:contrast · beat:turn · conf:verified · role:challenges
- Nationally, all data-center water withdrawals combined equal only about 5% of the water used on US golf courses — the crisis is local, not national — src:[S2] · purpose:contrast · beat:turn · conf:claimed · role:challenges
- Myth-check: grids plan years ahead (data centers don't inherently cause blackouts); diesel generators are emergency backup, not always-on; designs range from water-free air cooling to closed-loop — so "all data centers are water guzzlers" is false — src:[S5] · purpose:contrast · beat:turn · conf:claimed · role:challenges
- Even critics warn against hysteria: much viral panic (lights changing clouds, whole counties "wiped out") is false and discredits the legitimate concerns — src:[S2] · purpose:contrast · beat:turn · conf:verified · role:challenges
- Cooling is a genuine trade-off, not a free lunch: closed-loop/air cooling saves water but uses substantially more power, so there's "no real win" — src:[S1,S5] · purpose:contrast · beat:turn · conf:verified · role:context
- Efficiency won't save us (Jevons Paradox, 1860s): AI chips get more efficient, but cheaper compute drives more total demand, erasing the savings — src:[S4] · purpose:authority · beat:turn · conf:verified · role:supports
- Companies pledge to be "water positive" by 2030 and to use renewables/nuclear — but largely via credits/offsets, and at least 2028 before renewables power AI at scale (new nuclear a decade+ away) — src:[S1,S4] · purpose:contrast · beat:turn · conf:verified · role:challenges

## Beat: CLOSE (who pays, who decides)

- The jobs rarely materialize: even the largest data centers employ fewer than 150 permanent workers, some as few as 25; Stargate/Abilene will have ~100 full-time staff (a comparable cheese plant was projected at 500) — src:[S1,S2] · purpose:proof · beat:close · conf:verified · role:supports
- 37 states offer tax incentives; Virginia's 56 data-center projects got ~$1 billion in tax savings in one fiscal year; Meta (via "Silicat/Sidecat LLC") got 100% property-tax abatement for 15+ years in New Albany, OH (~$60M forgone) — src:[S1] · purpose:proof · beat:close · conf:verified · role:supports
- Residents often get all the downsides — noise, water strain, higher bills, lost homes — without a vote and without the tax windfall being passed back to them — src:[S1,S2] · purpose:transition · beat:close · conf:verified · role:supports
- Even boosters admit "the challenge is how quickly we can scale these up while minimally disrupting the communities they're built in" — the fight is about pace and consent, not the technology itself — src:[S5] · purpose:transition · beat:close · conf:verified · role:context

## needs-check (model knowledge — must stay softened in the script)

- The US electric grid in high-demand regions is decades old and expensive to upgrade — general background, not from these sources — src:[needs-check] · purpose:context · beat:evidence · conf:claimed · role:context
- Eminent domain requires "public use"/"public benefit" and fair-market compensation under the Fifth Amendment — general legal background (S2 asserts the "public good" framing) — src:[needs-check] · purpose:context · beat:evidence · conf:claimed · role:context
