# Bookworm Partnership Outreach Plan

A working document. Ordered for action. Update as outreach progresses — partners move between tiers, contacts get verified or corrected, hooks land or don't.

---

## Where Bookworm stands today

This is the real state of the project as of this writing — every claim below maps to working production code at <https://bookworm.guide>. Outreach pitches should be grounded in what is, not in what might be.

**Live and working:**

- **A live, free, BC-wide map** of Little Free Libraries at <https://bookworm.guide>. Anonymous to use, anonymous to contribute — no accounts.
- **39 libraries seeded** by the maintainer. The wider rollout will multiply this.
- **The "shelfie" feature** lets visitors photograph the current contents of a library so other readers can see what's on the shelves before walking over. Shelfies are auto-published on verified libraries.
- **A QR sticker funnel.** When a steward agrees, a Bookworm QR sticker on their library scans to `/here/`, geolocates the visitor, and resolves them to *that* library's page. From there: see the latest shelfie, leave a new one, or report an issue. Decision tree handles direct match (within 25m), ambiguous picker (25–100m), and no-match cases (no library within 100m → invite to add it).
- **A steward partnership flow** at `/partners/`. Stewards who receive the hand-delivered consent envelope can scan the QR on it to land on a short, branded form: where their library is, how to reach them, whether they want a sticker, whether they want to be a Library Hunt host stop, and an optional 140-char message for Hunt visitors.
- **Spam defenses** scaled for real-world use. Rate limits are loose for honest contributors (50 libraries / 10 min, 50 shelfies / 30 min), with progressive escalation on actual abusers. Honeypot fields, anti-bot timing, and admin moderation gate the rest.
- **Spatial duplicate flagging.** Libraries submitted within 20m of an existing entry are flagged for admin side-by-side review with three resolutions: approve as new, merge into existing, reject.
- **Privacy-preserving analytics.** QR scan outcomes (matched, picker shown, no match, denied, error) are logged with coordinates rounded to ~11m precision — enough to find unmapped libraries and tune the resolver, not enough to retrace anyone's path.

**Funded:**

- A Neighbourhood Small Grant application has been submitted through the Vancouver Foundation, administered by Mount Pleasant and Little Mountain Neighbourhood Houses, to cover ~$500 of QR sticker printing and steward envelope materials. **Decision pending** as of this writing.

**Not yet built:**

- Bookworm has no Instagram or other social presence yet. Several Tier 1 partners will look for one before responding — this is worth standing up before serious outreach begins.
- Partnership materials (poster, one-pager, email templates) are not yet drafted.
- The Library Hunt date is currently in the partnership form as **Saturday, August 15, 2026**. If this changes, update `forms.py` (the `hunt_interest` label) — it's the source of truth.

---

## Strategic frame

**The pitch is different for everyone.** A bookstore owner cares about why this brings book lovers to their door. A community organization cares about whether this serves their mission. A journalist cares about why their readers would care. A grant officer cares about measurable community benefit. Bookworm is the same project for all of them, but the *first sentence* is not.

**The ask escalates.** Lead with the lightest possible request. A "yes" to a poster opens a relationship — a "yes" to becoming a Library Hunt host stop later is much easier once that relationship exists. Never lead with the biggest ask.

**Tier 1 first, then awareness across Tiers 2–4.** Tier 1 (indie bookstores) gets in-person, phone, or email outreach with a real ask — a poster on the wall. Tiers 2–4 get awareness-level outreach (mostly email, lighter ask, often "we exist and you might find this interesting") that ramps up after the Library Hunt has a confirmed date.

**Visible traction matters.** A few of these conversations will go better if the asker can show, not just tell. Being able to point at: "39 libraries already mapped, here's the map, here's a steward who already partnered, here's an article about us" — each of those raises the conversion rate of the next pitch. Build social proof in tandem with outreach, not before it.

---

## Hook bank

Pull whichever hook fits the audience, not all of them.

| Audience | What they care about | Hook |
|---|---|---|
| Indie bookstores | Foot traffic, neighborhood literary identity, distinguishing from Amazon | "Bookworm sends curious readers walking through your neighborhood, then in your door." |
| Children's bookstores (Kidsbooks) | Family discovery, screen-free activities | "A wholesome neighborhood scavenger hunt that gets kids excited about books and walking." |
| Indigenous-owned bookstores (Massy, Iron Dog) | Place-based knowledge, community voices | "Mapping the informal book ecosystem already in our neighborhoods, by the people who use it." |
| Iron Dog specifically | Kindred-spirit recognition | "You roam the city bringing books to people. Little Free Libraries are the static version of the same idea — and we're mapping them." |
| Community orgs | Whether it serves their members | "A free tool your members can use, plus a Library Hunt event we'd love them to be part of." |
| Cycling orgs (HUB) | Active transportation, neighborhood exploration | "A wayfinding-by-bike activity built around an existing distributed community resource." |
| Local press | Local angle, civic-tech, indie-builder story | "A solo-built civic-tech project, fully working today, mapping a quietly beloved community institution across BC." |
| Grant officers / institutions | Measurable community benefit, alignment with their mission | "Stewardship-first community mapping with documented owner consent, privacy-preserving analytics, and a flagship event funded by a Neighbourhood Small Grant." |

A few notes on what's *now* sayable that wasn't sayable a few weeks ago:

- "**Stewards opt in**" is now a literal feature, not a promise. The `/partners/` form is live; the consent envelope flow is real.
- "**Scan the sticker, see what's on the shelf**" is now a literal feature. Visitors don't just *find* a library — they land on a page showing the latest shelfie.
- "**No accounts, no ads, no tracking**" is more credible now that scan analytics are publicly described as coordinate-rounded for privacy.
- "**Library Hunt — August 15, 2026**" is now a confirmed date in the steward form. Treat it as concrete in pitches; don't soften it to "later this year."

---

## Tier 1: Indie bookstores (priority)

The opening ask for all Tier 1 contacts is the same: **display a small Bookworm poster (with QR code) somewhere visible in the store**. Optional add-on: mention us in a newsletter or repost on social. The Library Hunt invitation comes later.

### Pulpfiction Books — *highest priority*

Two locations directly on/near where LFLs cluster: 2422 Main Street (Mount Pleasant) and 1744 Commercial Drive. Owner Chris Brayshaw is publicly outspoken about indie business, neighborhood character, and Amazon resistance — Bookworm's framing aligns.

- **Owner.** Chris Brayshaw (since June 2000)
- **Phone.** 604-876-4311 (Main) · 604-251-4311 (Commercial)
- **Email.** pulpbook@gmail.com
- **Social.** @pfbvan on Instagram and Twitter/X (active, ~4.5K followers)
- **Hours.** Main: Mon–Sat 10am–7pm, Sun 11am–7pm. Commercial: daily 11am–7pm.
- **Approach.** In-person drop-in at the Main Street location is ideal — Brayshaw is publicly known to value walk-in conversations with people who actually engage. Bring a printed poster mockup so the ask is concrete.
- **[Draft hook].** "I built a free tool that maps Little Free Libraries across BC, and Mount Pleasant is one of the densest clusters. The map is live at bookworm.guide. I'd love to put a small poster in your window — it'd send foot traffic past your door without competing with anything you sell."
- **Verify on day-of contact.** Call ahead to confirm Brayshaw is in. Hours change seasonally.

### Iron Dog Books — *highest strategic fit*

The bookmobile model is *literally* a roving Little Free Library philosophy made commercial. Indigenous-owned, Hastings Sunrise storefront, ~14K Instagram followers. Endorsement carries cultural and community weight.

- **Owners.** Hilary and Cliff Atleo (Anishinaabe / Nuu-chah-nulth / Tsimshian)
- **Storefront.** 2719 E Hastings St, Vancouver, daily 10am–6pm
- **Email.** Contact form at irondogbooks.com; older posts list Facebook DM as preferred for partnerships
- **Social.** @irondogbooks (Instagram, very active, ~14K followers)
- **Approach.** Email first, with explicit acknowledgment of the storefront and bookmobile. Lead lightly with the poster ask, mention the Library Hunt as a future possibility.
- **[Draft hook].** "Iron Dog and Bookworm have something in common — we both think books shouldn't be locked up in one place. Bookworm is a free, anonymous map of every Little Free Library in BC, live at bookworm.guide. I'd love to talk about a small partnership: a poster in the storefront for now, and possibly something more interesting if your bookmobile is interested in being a stop on the Library Hunt on August 15."
- **Care notes.** Indigenous-owned business; outreach should reflect that without overstating it. Don't position Bookworm as doing them a favor — be respectful that they're well-established and already do extensive community work.

### Massy Books — *high strategic fit, slower*

Owner Patricia Massy (Nêhiyaw-Métis) is Best of Vancouver bookstore (2023, 2025). Has weathered turbulence in the past year (unionization tensions, loss of living wage cert, Massy Arts gallery closure). Approach with awareness — this is not a "great year, ask big" moment.

- **Owner.** Patricia Massy
- **Address.** 229 E. Georgia St, V6A 1Z6
- **Phone.** 604-721-4405
- **Email.** patricia@massybooks.com (owner direct, per public contact page); info@massybooks.com (general)
- **Hours.** Mon–Sat 10am–6pm, Sun 11am–5pm
- **Approach.** Email the owner. Keep ask small (poster only). Acknowledge cultural work without effusiveness. Don't pitch the Hunt in the first message.
- **[Draft hook].** "I built a free, community-mapped guide to Little Free Libraries across BC, live at bookworm.guide. Stewards opt in via a consent flow. I'd love to put a small poster in Massy if you'd consider it — these libraries already exist in Chinatown and the Downtown East Side, and we're trying to make them more findable for the people who use them."

### The Paper Hound — *moderate fit, downtown anchor*

Downtown's "book row." Owners already run a free bicycle delivery service — alignment with neighborhood-mobility framing is built in.

- **Owners.** Kim Koch and Rod Clarke (opened 2013)
- **Address.** 344 W. Pender St, V6B 1T1
- **Phone.** 604-428-1344
- **Email.** thepaperhound@gmail.com
- **Hours.** Daily 10am–6pm
- **Approach.** In-person drop-in works well — small store, owners usually present.
- **[Draft hook].** "You already deliver books by bike to half the city. I built a free tool that maps Little Free Libraries across BC — bookworm.guide — and I think your customers are exactly the people who'd use it. Could I leave a small poster?"

### Upstart & Crow — *programming-focused*

Now operating as a non-profit dedicated to amplifying stories. Programming partnerships, residencies, events — Bookworm fits their orbit more than their commerce.

- **Founders.** Ian Gill and Zoë Grams
- **Programming partnerships.** tomie@upstartandcrow.com
- **General.** hello@upstartandcrow.com
- **Address.** 1387 Railspur Alley, Granville Island
- **Phone.** 604-558-1124
- **Hours.** Tues–Fri 10:30–5:30, Sat–Sun 10–6
- **Approach.** Email tomie@. Lead with poster ask, mention possible programming fit.
- **[Draft hook].** "Upstart & Crow's mission to amplify storytelling resonates with what we're trying to do at Bookworm — we map the informal storytelling network already in BC's neighborhoods. The map is live at bookworm.guide. I'd love to start with something small (a poster) and explore whether there's anything bigger that might fit your programming — there's a Library Hunt event coming August 15."

### Book Warehouse (Main + Broadway) — *easy yes, broader audience*

Two Central Vancouver locations (4118 Main, 632 W Broadway) plus a third at 108 E Broadway. Higher walk-in volume than the curated indies. Part of Black Bond Books.

- **Owner.** Cathy and Mel Jesson (Black Bond Books)
- **Phones.** 604-879-7737 (Main) · 604-872-5711 (Broadway)
- **Web.** bookwarehouse.ca / blackbondbooks.com
- **Approach.** Drop-in. Likely an easy yes for poster, less likely to amplify socially. Numbers play.
- **[Draft hook].** Same as Pulpfiction template; keep simple.

### Kidsbooks — *children/families angle*

2557 W Broadway, Kitsilano. Phyllis Simon (founder, 1983, former librarian); Kelly McKinnon (co-owner since 1990). Different audience, unique value: Library Hunt as a family activity. Many LFLs are stocked with kids' books.

- **Address.** 2557 W Broadway, V6K 2E9
- **Phone.** 604-738-5335
- **Hours.** Mon–Sat 10–5:30, Sun 11–5:30
- **Approach.** Phone or in-person; a written pitch could feel cold for the relational style of this store. Phyllis's endorsement could later unlock the school librarian network.
- **[Draft hook].** "I built a free, family-friendly tool that maps Little Free Libraries across BC — bookworm.guide. We're running a community Library Hunt on August 15, kid-and-parent friendly. I'd love to start by leaving a small poster, and I'd value your perspective on whether something like this might be useful to the families who shop with you."

### Macleod's Books — *book row legend, optional*

455 W Pender. Vancouver institution but old-school owner, doesn't engage with social media. Worth a drop-in if doing a "book row" sweep when visiting Paper Hound. Low expectations.

---

## Tier 1.5: Library Hunt host candidates

After "yes" to a poster, these are the natural follow-ups:

- **Iron Dog Books** — bookmobile as roving "Hunt HQ" or end-of-day gathering point. Strongest pitch.
- **Pulpfiction Main** — neighborhood anchor for the Mount Pleasant section.
- **Upstart & Crow** — co-host literary kickoff event; their space is event-ready.
- **Massy Books** — likely too operationally stretched right now; revisit in 6 months.

Don't pitch the Hunt to anyone in Tier 1 until they've said yes to the poster. Two yeses are easier than one big yes.

---

## Tier 2: Local press (awareness, post-event-announcement)

Pitch *after* the Library Hunt has been announced more broadly — that gives reporters a date and a hook.

### Scout Magazine

- **Why.** Andrew Morrison (editor/publisher) explicitly champions small independent businesses. Bookworm fits the "Vancouver Would Be Cooler If…" / "1,000 Cool Things About Vancouver" lanes.
- **Editor.** Andrew Morrison (editor-in-chief), Michelle Sproule (managing editor).
- **Email for pitches.** scoutmagazine@gmail.com (per their "Write for Scout" page).
- **Approach.** Email pitch when there's an event hook. Keep under 300 words. Lead with the human-interest angle — solo developer, BC-only, neighborhood-by-neighborhood, stewards opt in.

### The Tyee

- **Why.** Independent BC-focused journalism, covers civic-tech and community organizing. Has previously covered both Massy Books and other local literary projects.
- **Approach.** Their tip line / general contact form. Pitch as "BC's Little Free Libraries are getting their first map." The provincial angle matters.

### Stir Vancouver

- **Why.** Arts/culture digital coverage. They covered Upstart & Crow's opening — they like literary/community angles.
- **Approach.** Editorial contact via their site. Same event-hook timing as Scout.

### CBC Vancouver

- **Why.** They've covered both Pulpfiction and Iron Dog Books in human-interest pieces. The Library Hunt could be radio gold (Stephen Quinn's *On the Coast* or *The Early Edition*).
- **Approach.** Pitch closer to the Hunt date. Story producers prefer 2–3 weeks lead time.

### Daily Hive Vancouver / Vancouver Is Awesome

- **Why.** High-volume local content sites that aggregate Vancouver "things to do." Lower bar for coverage, broader reach.
- **Approach.** Tip submission forms on each site, closer to event date.

### Georgia Straight

- **Why.** Voted Massy Books "Best Bookstore" in 2025. They cover indie literary culture.
- **Approach.** Editorial pitch when there's an event.

**Verify before pitching:** the editorial contacts above are pulled from public-facing pages but should be re-checked at point of contact — staff turnover happens.

---

## Tier 3: Adjacent community organizations

### HUB Cycling — *highest active-partner potential*

~3,000 members and 65,000 supporters across Metro Vancouver. They run group rides, education, "Go by Bike Week" (twice yearly), and an annual Bicycle Film Festival. Their published strategy explicitly seeks "creative cross-promotional partnerships."

- **Events partnerships.** events@bikehub.ca
- **Executive Director.** Rose Lipton
- **Director of Program Development.** Tim Jervis (since 2013)
- **Approach.** Email events@bikehub.ca. The ask is bigger here — co-promoted Library Hunt ride, possibly tied to Go by Bike Week if the dates align.
- **[Draft hook].** "Bookworm is a free, live map of Little Free Libraries across BC at bookworm.guide. I'm running a Library Hunt on August 15 where participants visit and document libraries by bike across neighborhoods. This is fundamentally a HUB-style activity. I'd love to talk about whether HUB might co-promote or host a ride."

### Neighborhood Houses

These are the *administrators* of the Neighbourhood Small Grants Bookworm applied to. Worth introducing yourself even if the grant doesn't come through.

- **Mount Pleasant Neighbourhood House** — 800 E Broadway. Verify email at point of contact.
- **Little Mountain Neighbourhood House** — co-administering the grant Bookworm applied to.
- **Kitsilano Neighbourhood House** — 2305 W 7th Ave.
- **Cedar Cottage Neighbourhood House** (East Van overflow) — 4065 Victoria Dr.
- **Gordon Neighbourhood House** (downtown/West End) — 1019 Broughton St.
- **Approach.** After the grant decision lands, regardless of outcome. Frame it as "introducing myself as a community-mapping project in your catchment, would love to know if you have programming this might fit." Post-grant outreach is more honest than pre-grant outreach.

### Vancouver Public Space Network (VPSN)

Civic-engagement org for public space. Direct mission overlap. Good for amplification on social and possibly a guest blog post.

- **Web.** vpsn.ca
- **Approach.** Email their general contact, offer a guest post about the project. Lower commitment, higher visibility.

### BC Libraries Cooperative

Provincial library cooperative. Long-term: potential fiscal sponsor for grant eligibility without nonprofit incorporation. Defer until post-Hunt.

---

## Tier 4: Schools and youth (deferred, ~12 months)

Documented for completeness:

- VPL Reading Buddies (branch programs)
- Vancouver School Board literacy coordinators
- Frontier College
- Out in Schools

Re-evaluate after the first Library Hunt has happened.

---

## Outreach materials to build first

These are deliverables the next chat (or Ben directly) should produce before significant outreach happens. Priority order:

1. **A printed poster mockup with QR code.** The single most important piece. The QR should land on `bookworm.guide/here/` (the live route). Bookworm aesthetic — warm teal/forest, Fraunces display type, not generic. 8.5×11 and 11×17 sizes. Include a short "what is this?" line, the URL, and a small attribution to the grant funder.
2. **A 30-second elevator pitch.** Verbal, audience-flexible. Should match the audience's hook from the table above.
3. **Email templates.** One for indie bookstores, one for community orgs, one for press. Each ~5–7 sentences, with personalization slots clearly marked. The bookstore template should reference `bookworm.guide` and the live `/here/` flow concretely; the press template should reference the Hunt date.
4. **An "About Bookworm" one-pager.** Leave-behind for in-person drops, attachment for email. Different from the steward envelope: this is for *partners*, not stewards. Should include: what Bookworm is, the QR sticker funnel, the steward consent process, the Hunt, contact info, and live URLs. Single sided, partner-tone (not steward-tone).
5. **A lightweight Bookworm Instagram presence.** Not a marketing channel — a credibility check. Bio, link to map, half a dozen launch-quality posts (some of the existing 73 shelfies, the project story, a "what is a Little Free Library" explainer, a Hunt save-the-date). Several Tier 1 partners will look for this before responding.

---

## Outreach sequencing

**Week 1 (now):** Build outreach materials 1–4. Stand up Instagram (item 5). Don't contact partners yet.

**Week 2:** First wave of Tier 1 contacts.
- In-person drops at Pulpfiction Main, Paper Hound, Book Warehouse Main, Kidsbooks. 1–2 stores per outing.
- Email Iron Dog, Massy, Upstart & Crow.
- Email HUB Cycling.

**Weeks 3–4:** Polite second contacts on non-responses. If grant decision is back, open Neighborhood House outreach. If Library Hunt is publicly announced, open Tier 2 press conversations.

**Week 5+:** Tier 1.5 Library Hunt host conversations with whichever Tier 1 partners said yes. VPSN guest post pitch. Plan Word Vancouver (September) / Writers Fest (October) presence.

---

## Tracking

Suggested column-set for whatever tool is chosen (Notion, Google Sheets, Airtable):

| Partner | Tier | Contact name | Contact channel | Date contacted | Response | Status | Next action | Notes |

The point is not losing track when 8 conversations are running in parallel. Each row should also track which version of the outreach material was sent (so when the poster mockup updates, you know who saw which version).

---

## Open questions for outreach work

1. Should the QR poster code deep-link to a poster-specific landing (`/here/?source=poster`) for analytics, or use the same `/here/` route as physical stickers? *(Tradeoff: simpler stack vs. measurable funnel attribution. Recommend asking the engineering chat after outreach plan stabilizes.)*
2. Is the Library Hunt definitely a single Saturday, or a Saturday-and-Sunday window? Affects partner commitment framing for Iron Dog (would the bookmobile be available both days?) and for HUB (one ride or two?).
3. For Iron Dog and Massy specifically — these emails should be drafted carefully, given their cultural significance. Worth having someone review before sending.
4. Is the maintainer comfortable being identified by name in pitches and press? "Solo developer" can be left anonymous in a poster but reporters will want a person to name. Decide before press outreach.

---

*Last updated: shortly after Phase 3 deployment. Update as outreach progresses. Move partners between tiers freely as conversations evolve.*
