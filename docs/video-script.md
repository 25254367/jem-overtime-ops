# 5-minute video — script / talking notes

Camera on, screen shared. Not a pitch — think out loud, pauses are fine.
`[ ]` = what to show. `>` = roughly what to say (~620 words ≈ 5 min with clicks).
Numbers are live from the pipeline — round them when you speak.

---

## 0:00 – 0:35 · What it is + show it working

[ Dashboard open, **Now** tab. ]

> Ops-room dashboard for the contract manager who runs six facilities sites,
> about 213 shift workers. Today the client only finds out about overtime on
> Monday, after payroll. This answers: it's Wednesday, the week isn't over —
> who breaches the 10-hour overtime cap by Sunday, and what does someone do
> about it today.

[ Point at the tiles, expand one person. ]

> Five predicted breaches, eight to watch, about R12,000 of projected overtime.
> Each person gets a plain-English projection, nine weeks of history, and one
> concrete action — a named fix, not "monitor overtime".

---

## 0:35 – 0:50 · Loads next week with no developer

[ "Load next week's data" → drop in `data_next_week/` → Validate & run. ]

> Next week's data doesn't need me — drop in the seven CSVs, it checks the
> columns and recomputes. This one runs through Friday, so the banner re-fits
> and says the accuracy's higher. A broken file fails with a readable message.

---

## 0:50 – 1:30 · What I didn't expect

[ "Fix these first" card. ]

> What I didn't expect: five people are in the register twice — two employee
> IDs, same ID number, bank account, tax number. One person, one record per
> site.

> Each record on its own sits in the 30s — invisible. Combined they're mid-50s
> to low-70s, breaching most weeks. The client's Monday report can't see these
> five at all.

> And it cascades — on the days they're at one site, the other logs a no-show
> and pays a cover, 39 times in ten weeks, with about 510 hours billed at two
> sites at once. One data-entry problem, three costs.

---

## 1:30 – 2:20 · Baseline, metric, why that metric

> Is it any good — I backtested it: for every past week, pretend it's
> Wednesday, train on earlier weeks only, predict, check.

> Base rate's about 5%, so "predict nobody breaches" scores 95% accuracy and is
> useless — which is why I don't report accuracy. The naive baselines either
> catch one breach in five, or flag ten people for every real one. Mine catches
> about half, with about half its flags real.

> I optimise for recall — a false alarm costs a phone call, a missed breach is
> a compliance breach nobody saw coming. That's the expensive error.

> One caveat: about half that score is the five duplicate-ID people, who are
> easy. For an ordinary employee it's weaker.

---

## 2:20 – 3:15 · One number, start to finish

[ Pieter Khumalo's row, expanded. ]

> One number, end to end. Pieter Khumalo, guard at Menlyn Park.

> By Wednesday he's worked three shifts, about twelve hours each — clock-out
> minus clock-in, added up, 36 hours. That's three-quarters of a normal week
> for him, and it's only Wednesday.

> The obvious move is to scale up: 36 in three days is 84 in seven — "certain
> breach". But his history says no. He's never actually hit 60; he front-loads
> then eases off; his normal week is about 49.

> So the model doesn't multiply. Measured across everyone, for each hour you're
> ahead by Wednesday, about three-quarters of an hour comes back off the
> weekend. From 36 it expects about 16 more — finishing around 53.

> 53 is under the 55 limit — so why is his risk 33%, not zero? Because some
> weeks he picks up a fifth shift, which is exactly when he's breached before.
> Roughly one in three. That's the number.

---

## 3:15 – 3:55 · Where I wouldn't trust it

[ Point at the "accuracy: moderate" banner. ]

> Where I don't trust it: about 40% of real breaches score under 0.10 on
> Wednesday — the model says they're fine. A better model doesn't fix that.
> Those breaches come from shifts added Thursday to Sunday, and there's no
> roster in the data — nothing on Wednesday sees them.

> So the banner's honest: Wednesday is "moderate", and it climbs through the
> week. Saturday is nearly certain; Monday is a hint.

---

## 3:55 – 4:35 · Next two days

> With two more days: get the roster and the leave calendar — the one missing
> input, it closes most of that 40% gap. Refresh daily instead of one Wednesday
> snapshot. And the real one — push week-to-date hours upstream to whoever
> assigns weekend shifts, so a breach gets prevented, not just predicted. For
> the notes, once it's more than one client, swap the rules for a language
> model.

> Thanks.

---

## If you run long — cut in this order
1. The next-week demo at 0:35 → "and it reloads next week's data with schema checks".
2. The two named baselines → "it beats the naive baselines".
3. The "scale up: 84 in seven" line — go straight from 36 hours to the history.

## Alternative "one number" — a classified note (swap for the risk-score block)
> Note S106395: "covering Mthembu postt, no show no call" — misspelt. The system
> saw "covering", "post", "no show" → the "someone didn't turn up" pile, and
> "Mthembu" is a name so it logged who was covered for. No AI — about fifty
> phrases plus typo-tolerance to match "postt". Checked two ways: hand-labelled
> 180 notes, 100% on the random sample; and a different method agreed on 95% of
> all 2,100.
