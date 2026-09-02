# Hand-labelling guide — `gold_sample.xlsx`

180 notes to label by hand, **before** looking at any classifier output. This
is the gold set the classifier is measured against (README Requirement 3).
Fill in `gold_sample.xlsx` (dropdowns are built in); `.csv` is the same content
if you'd rather use that.

The worksheet has only what `shift_notes.csv` contains — `shift_id`,
`logged_by`, `note` — so your labels are made from the **same information the
text classifier gets**. (`logged_by` is just the supervisor's code; it carries
no category signal — ignore it.)

Fill from the **note text alone**:

| column | every row? | what to put |
|---|---|---|
| `label` | yes | one of the 7 categories (dropdown) |
| `absence_reason` | only if `label = absence_cover` | `no_show` / `sick` / `leave` / `unknown` (dropdown) |
| `authorised` | only if `label = client_requested` | `yes` (signed off / approved / ok'd) or `unclear` (dropdown) |
| `absentee` | only if `label = absence_cover` and a person is named | the surname, e.g. `Mokoena`; or `unnamed_relief` for a relief/next-shift with no name; else blank |
| `confidence` | yes | `confident` or `ambiguous` (dropdown) |
| `comment` | as needed | `lie` for notes that lie; a word you can't translate; why you picked one label over another |

---

## `label` — pick exactly one of 7

**Categories that carry a reason for extra hours:**

| label | it means | signals |
|---|---|---|
| `client_requested` | the client / centre management / site manager asked for extra cover, patrol, cleaning, or for staff to stay | "requested by centre management", "client asked us to stay", "deep clean before the audit", "extra man on the gate for the event", "klient het ekstra ure gevra", "stocktake ran over, client asked us to remain" |
| `absence_cover` | someone who should have been on post wasn't — relief no-show, a named colleague absent / sick / on leave, or one guard covering two posts | "next shift did not pitch", "relief no show", "covering X post, no show no call", "X didnt come in, covered the post", "X akezanga namhlanje, ngimele yena", "covering for X - booked off sick", "double duty, X on family responsibility leave", "took X shift as well, 2 posts 1 guard", "aflos het nie opgedaag nie, moes aanbly", "no replacement sent" |
| `late_handover` | handover delayed — waiting on paperwork / keys / OB book, or the next person just late | "late handover, waiting on paperwork", "oorhandiging was laat, gewag vir sleutels", "handover late again, keys missing", "waited 25 min for handover, ob book not signed" |
| `equipment_failure` | machine / generator / lift / gate broke; work done manually or took longer | "generator fault, stayed to monitor", "buffer machine kaput, did the floor by hand", "scrubber broke down", "lift out of order", "masjien is stukkend, alles met die hand gedoen", "gate motor failed" |

**Categories that do NOT carry a reason:**

| label | it means | signals |
|---|---|---|
| `routine` | an actual statement that the shift was uneventful | "quiet shift", "nothing to report", "no incidents", "all quiet", "all good", "all fine", "no issues on site", "as per normal", "akukho lutho", "niks om te rapporteer nie" |
| `blank` | empty, punctuation only, or a bare acknowledgement token | "", "-", ".", "n/a", "ntr", "ok", "sharp", "fine", "noted" |
| `unclassified` | there is real text but it does not fit any category above, or it's too garbled to read | — |

### Decision order (when more than one seems to fit)
1. **Note that lies** — if the surface says client-requested but the note itself
   says the real reason was a no-show / cover ("client signed for the extra hrs
   **but real reason is relief no show**"), label it `absence_cover` and write
   `lie` in `comment`.
2. Otherwise, most concrete cause wins: `equipment_failure` > `absence_cover` >
   `late_handover` > `client_requested`.
3. Any reason category beats `routine` / `blank`.
4. `routine` needs a *statement* that the shift was uneventful ("all quiet",
   "all good", "no incidents"). Bare acknowledgement tokens — "ok", "sharp",
   "fine", "noted", "-", "." — are `blank`.

---

## `absence_reason` — only for `absence_cover`

- `no_show` — didn't come, no call, didn't pitch, `akezanga`, `het nie opgedaag nie`
- `sick` — booked off sick, at the clinic, `siek gemeld`
- `leave` — family responsibility leave, on leave
- `unknown` — cover is clear but no reason given

## `authorised` — only for `client_requested`

- `yes` — "signed off", "approved", "ok'd by centre mgmt", "per client email approved by office"
- `unclear` — "client says stay… dont know if office approved" (a billing-risk note)

## `absentee` — only for `absence_cover`

- Named absent person → their surname (e.g. `Mokoena`).
- Unnamed relief / next shift / replacement → `unnamed_relief`.
- `absence_cover` but no one identifiable → leave blank.

---

## `confidence` — confident / ambiguous

`ambiguous` if you had to guess, the note is borderline between two labels, or
you can't fully read it. Be honest — the check reports accuracy on the
`confident` subset separately.

## `comment` — free text, optional

Use it for: `lie` (notes that lie), why you picked one label over another,
a word you couldn't translate, "typo for X", anything a reviewer should know.

---

## Multilingual quick reference

**isiZulu:** *akezanga / akafikanga* = did not come · *namhlanje* = today ·
*ngimele yena / ngihlale* = I stood in / I stayed · *akukho lutho* = nothing ·
*ngicela* = please · *kuze kube* = until

**Afrikaans:** *aflos* = relief · *het nie opgedaag nie* = did not show up ·
*moes aanbly* = had to stay on · *gedek vir* = covered for · *siek gemeld* =
reported sick · *oorhandiging* = handover · *gewag vir sleutels* = waited for
keys · *masjien is stukkend* = machine is broken · *met die hand gedoen* = done
by hand · *klient het ekstra ure gevra* = client asked for extra hours ·
*niks om te rapporteer nie* = nothing to report
