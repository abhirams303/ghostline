# GHOSTLINE — 90-Second Demo Script

**Total spoken time:** ~90 seconds at natural pace (~225 spoken words).
**Voice agent:** 6 registered tools (`set_active_location`, `get_location_assessment`, `get_cascade_analysis`, `get_adversary_actions`, `compare_all_locations`, `get_live_situation`).
**Backed by:** 145 Palantir Foundry objects (5 GeoFeatures, 36 Units, 11 Platforms, 72 Sensors, 5 Assessments, 5 Cascades, 11 Adversary Actions). All offline-resilient via `backend/ai/demo_cache/` (43 files).

---

## [0:00–0:10]   Open — Fort Liberty baseline

**OPERATOR SPEAKS:** *"Show me Fort Liberty."*

**BOT RESPONDS:**
> "Fort Liberty on the deck."

**SCREEN SHOWS:** deck.gl map flies to (35.14, -79.15). Green target marker drops on base. Amber ring of 12 linked-unit markers spreads around it. Red live-aircraft markers (real-time FlightRadar24) populate inside the 25 nm radius. IntelPanel on the right empties — ready for assessment data.

---

## [0:10–0:30]   Surface assessment — the baseline number

**OPERATOR SPEAKS:** *"What's the threat brief?"*

**BOT RESPONDS:** *(calls `get_location_assessment`)*
> "Fort Liberty. Exposure score seventy-eight. HIGH risk. Nine distinct Strava exercise routes are publicly visible on the perimeter, peak activity 0600 to 0700. Aircraft predictability seventy-one out of one hundred. Sentinel-1A satellite pass in three point seven hours at seventy-three degrees elevation."

**SCREEN SHOWS:** ScoreStrip lights up with `aggregate=78` (HIGH), sub-scores `movement=78`, `personnel=48`, `facility=100`, `aerial=71`. IntelPanel "Sector" tab fills with the threat brief.

---

## [0:30–1:00]   Norfolk showcase — cascade depth 94

**OPERATOR SPEAKS:** *"Switch to Naval Station Norfolk and show me the cascade."*

**BOT RESPONDS:** *(calls `set_active_location` then `get_cascade_analysis`)*
> "Naval Station Norfolk. Cascade score one hundred — capped. Chain depth ninety-four. Twelve units, ten platforms, seventy-two sensors compromised downstream. Surface exposure propagates through Carrier Strike Group Twelve and DDG-81, exposing AN/SPY-1 radar and AN/SQQ-89 sonar capabilities. Recommended mitigation: harden emissions discipline across Carrier Strike Group Twelve."

**SCREEN SHOWS:** Map flies to Norfolk piers (36.94, -76.30). Amber markers cluster on the carrier piers (12 units). 26 red aircraft markers populate the bay. IntelPanel "Findings" tab shows 4 findings — the **AN/SPY-1 cyber-disruption finding sits at CRITICAL severity**.

---

## [1:00–1:20]   Adversary modeling — what they'd actually do

**OPERATOR SPEAKS:** *"What would an adversary do with that?"*

**BOT RESPONDS:** *(calls `get_adversary_actions`)*
> "Three predicted actions. Highest priority — cyber-disruption against AN/SPY-1 mounted on DDG-81. Capability required: persistent network access. Timeline: weeks. Second — surveillance of CVN-75. Third — kinetic planning against Naval Station Norfolk itself."

**SCREEN SHOWS:** AdversaryAction panel populates with 3 cards. The disruption card highlights `target=AN/SPY-1`, `target_id=sens_an_spy_1__ddg_81__unit_carrier_strike_group_twelve` — a real chain entity, not invented.

---

## [1:20–1:30]   Leaderboard — the architectural argument

**OPERATOR SPEAKS:** *"Compare all the bases."*

**BOT RESPONDS:** *(calls `compare_all_locations`)*
> "Naval Station Norfolk and Fort Liberty tied at one hundred — HIGH. Joint Base Lewis-McChord eighty-six — HIGH. JBLM's surface score was only forty-two, MEDIUM — but cascade analysis through the Stryker Brigade chain pushes it into HIGH. Shack15 fifty-five. Naval Base San Diego thirty-three."

**SCREEN SHOWS:** Leaderboard panel renders 5 ranked rows. JBLM's row visually pops — its surface bar sits at 42, but its cascade bar reaches 86. **That gap IS the demo.**

---

## Beat-by-beat timing

| Beat | Operator | Bot | Tool latency | Cumulative |
|------|---------:|----:|-------------:|-----------:|
| Open | 1.5 s | 2 s | ~1 s | 4.5 s |
| Assessment | 2 s | 13 s | ~2 s (cached) | ~22 s |
| Norfolk + Cascade | 3 s | 18 s | ~3 s | ~46 s |
| Adversary | 2 s | 12 s | ~2 s | ~62 s |
| Compare | 1.5 s | 14 s | ~1 s | ~78 s |
| Buffer / pause | — | — | — | ~90 s |

**Total: ~90 seconds.** Cache-served paths keep tool latencies near zero, leaving the time budget on bot narration and the screen reaction.

## Failure-mode fallbacks (rehearsal-only)

- **Foundry unreachable:** `backend/ai/demo_cache/` (43 JSON files, ~470 KB) serves last-known good responses. Norfolk's AN/SPY-1 narrative + cascade depth 94 are preserved on disk — verified live by deleting `.env` and re-hitting `/voice/get_cascade`.
- **FR24 rate-limited:** live aircraft layer disappears, the rest of the report still lands. Cached Sentinel passes still narrate.
- **OpenAI down for the bot's LLM:** voice agent can't form sentences; demo continues silent on the deck.gl side, all panels still populate from cached endpoints.
