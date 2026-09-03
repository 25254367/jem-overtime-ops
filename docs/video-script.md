# 5-minute video — script / talking notes

Camera on, screen shared. Not a pitch — think out loud, it's fine to pause.
`[ ]` = what to show. `>` = roughly what to say (~700 words ≈ 5 min with clicks).
Numbers are live from the pipeline — round them when you speak.

---

## 0:00 – 0:35 · What it is + show it working

[ Dashboard open, **Now** tab. ]

> This is an ops-room dashboard for the contract manager who runs six
> facilities sites — about 213 shift workers. Today the client only finds out
> about overtime on Monday, once payroll's run. This answers: it's Wednesday,
> the week isn't over — who breaches the 10-hour overtime cap by Sunday, and
> what can someone do about it today.

[ Point at the tiles, then expand one person. ]

> Five predicted breaches, eight to watch, about R12,000 of projected overtime.
> Each person gets a plain-English projection, nine weeks of history, and one
> concrete action — not "monitor overtime", an actual named fix.

---

## 0:35 – 0:50 · Loads next week with no developer

[ "Load next week's data" panel → drop in `data_next_week/` → Validate & run. ]

> Loading next week doesn't need me — drop in the seven CSVs, it checks the
> columns and recomputes. This export runs through Friday, so the banner
> re-fits and says the accuracy's higher. A broken file fails with a readable
> message.

---

## 0:50 – 1:35 · What I didn't expect

[ "Fix these first" card. ]

> The thing I didn't expect: five people are in the register twice — two
> employee IDs, same ID number, same bank account, same tax number. One person,
> one record per site.

> Each record on its own sits in the 30s — under the limit, invisible.
> Combined they're in the mid-50s to low-70s, breaching most weeks. The
> client's Monday report can't see these five at all.

> And it cascades: on the days they're at one site, the other logs a no-show
> and pays a cover — 39 times in ten weeks — and about 510 hours get billed at
> two sites at once. One data-entry problem, three real costs.

---

## 1:35 – 2:35 · Baseline, metric, why that metric

> Is the answer any good — I backtested it. For every past week I pretend it's
> Wednesday, train only on earlier weeks, predict, check what actually happened.

> The base rate is about 5%, so "predict nobody breaches" is 95% accurate and
> useless — that's why I don't report accuracy. Two real baselines: flag anyone
> whose average is over the limit catches one breach in five; just extrapolate
> hours-so-far flags ten people for every real breach, because Monday's a
> public holiday and front-loads the week.

> Mine catches about half the breaches with about half its flags real. I
> optimise for **recall** — a false alarm is a phone call, a missed breach is a
> compliance breach nobody saw coming. That's the expensive error, so that's
> what I tune against.

> One honest caveat: about half that score comes from the five duplicate-ID
> people, who are easy. For an ordinary employee it's weaker.

---

## 2:35 – 3:25 · One number, explained simply

[ Pieter Baloyi's row, expanded. ]

> One number end to end. Pieter Baloyi, supervisor at Sandton City — 46% chance
> he breaches. Where's 46 from — three things, no black box.

> One: by Wednesday he's done 28 hours.
> Two: over nine weeks he normally lands around 51 — close to the 55 limit — and
> he's tipped over three of those nine weeks. He works right at the line.
> Three: 28 by Wednesday is a slightly busy start, so I nudge his finish up to
> about 55.

> 55 is exactly the limit, so it's near a coin toss — that's the 46%. If he'd
> done 35 by Wednesday it'd be about 62%, because then he's clearly running hot.
> That's the model: where is he now, where does he usually end up, how close is
> that to the line.

---

## 3:25 – 4:05 · Where I wouldn't trust it

[ Point at the "accuracy: moderate" banner. ]

> Where I don't trust it: about 40% of real breaches score under 0.10 on
> Wednesday — the model says they're fine. That's not something a better model
> fixes. Those breaches come from shifts added Thursday to Sunday, and there's
> no roster in the data — nothing on Wednesday sees them.

> So the banner is honest: on Wednesday the accuracy is "moderate" and it climbs
> through the week. A Saturday prediction is nearly certain; a Monday one is a
> hint.

---

## 4:05 – 4:45 · Next two days

> With two more days: get the roster and the leave calendar — that's the one
> missing input, it closes most of that 40% gap. Refresh daily instead of one
> Wednesday snapshot. And the real one — push week-to-date hours upstream to
> whoever assigns weekend shifts, so a breach gets prevented, not just
> predicted. For the notes, once it's more than one client, swap the rules for
> a language model.

> Thanks.

---

## If you run long — cut in this order
1. The next-week demo at 0:35 (just say "and it reloads next week's data with schema checks").
2. The two named baselines → "it beats the naive baselines".
3. The "if he'd done 35 hours" line.

## Alternative "one number" — a classified note (swap for the risk-score block)
> Note S106395: "covering Mthembu postt, no show no call" — misspelt. My system
> saw "covering", "post", "no show" and put it in the "someone didn't turn up"
> pile, and "Mthembu" is a name so it logged who was covered for. No AI — about
> fifty phrases plus typo-tolerance to match "postt". I checked it two ways:
> hand-labelled 180 notes, 100% on the random sample; and a totally different
> method agreed on 95% of all 2,100.
